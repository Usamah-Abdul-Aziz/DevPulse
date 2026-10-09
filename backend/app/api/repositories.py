"""Repository endpoints: connect a repo, list connected repos, read one back.

`POST /connect` is the only write endpoint in Phase 2 and it is deliberately asynchronous
(AGENTS.md: ingestion never blocks a request). It validates everything it can synchronously —
allow-list membership, token presence, the `owner/name` format — then hands the real work to a
background task and answers **202** with the job id. The client polls `GET /jobs/{job_id}`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import HTTPProblem
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.dates import as_utc
from app.ingestion.runner import IngestionRunner, get_ingestion_runner
from app.models import IngestionJob, Repository
from app.models.ingestion_job import JOB_ACTIVE_STATES
from app.schemas.pagination import Page, clamp_limit
from app.schemas.repository import (
    ConnectResponse,
    LatestJobSummary,
    RepositoryConnectRequest,
    RepositoryDetail,
    RepositorySummary,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/connect", response_model=ConnectResponse, status_code=status.HTTP_202_ACCEPTED)
def connect(
    request: RepositoryConnectRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    runner: IngestionRunner = Depends(get_ingestion_runner),
) -> ConnectResponse:
    """Connect a public repository and start an ingestion job.

    Returns **202** immediately; the job runs in the background. Existing running or pending jobs
    for the same repository are returned as-is, so the call is idempotent.
    """
    full_name = request.repository

    # Fail closed: an unset allow-list must never mean "everything is allowed".
    if not settings.allowed_repos:
        raise HTTPProblem(
            status.HTTP_400_BAD_REQUEST,
            "No repositories are allowed. Set ALLOWED_REPOS (comma-separated 'owner/name') "
            "before connecting one.",
        )
    if full_name.lower() not in {entry.lower() for entry in settings.allowed_repos}:
        raise HTTPProblem(
            status.HTTP_403_FORBIDDEN,
            f"'{full_name}' is not in the ALLOWED_REPOS list.",
        )
    if not settings.github_token:
        raise HTTPProblem(
            status.HTTP_400_BAD_REQUEST,
            "GITHUB_TOKEN is not configured; ingestion cannot authenticate to GitHub.",
        )

    owner, name = full_name.split("/", 1)
    repository = db.scalars(
        select(Repository).where(Repository.owner == owner, Repository.name == name)
    ).one_or_none()

    if repository is None:
        repository = Repository(owner=owner, name=name, full_name=full_name)
        db.add(repository)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            repository = db.scalars(
                select(Repository).where(Repository.owner == owner, Repository.name == name)
            ).one()
        db.refresh(repository)

    job = _existing_job(db, repository.id)
    if job is None:
        job = IngestionJob(repository_id=repository.id, status="pending")
        db.add(job)
        db.commit()
        db.refresh(job)
        background_tasks.add_task(runner, job.id)
    else:
        # A paused job that is due to resume gets re-queued instead of a new one.
        if job.status == "paused" and _is_due_for_resume(job):
            job.status = "pending"
            db.commit()
            background_tasks.add_task(runner, job.id)

    return ConnectResponse(job_id=job.id, repository_id=repository.id, status=job.status)


def _is_due_for_resume(job: IngestionJob) -> bool:
    """True when a paused job's rate-limit window has passed (or was never recorded)."""
    if job.resume_after is None:
        return True
    return as_utc(job.resume_after) <= _now()


def _existing_job(db: Session, repository_id: int) -> IngestionJob | None:
    """A job this connect should *not* replace: anything running or pending, else the last pause.

    A paused job is returned even when it is due for resume — the caller re-queues *that* row
    rather than starting a fresh one, so the stored cursor survives.
    """
    pending = db.scalars(
        select(IngestionJob)
        .where(
            IngestionJob.repository_id == repository_id,
            IngestionJob.status.in_(JOB_ACTIVE_STATES),
        )
        .order_by(desc(IngestionJob.id))
    ).first()
    if pending is not None:
        return pending

    return db.scalars(
        select(IngestionJob)
        .where(
            IngestionJob.repository_id == repository_id,
            IngestionJob.status == "paused",
        )
        .order_by(desc(IngestionJob.id))
    ).first()


@router.get("", response_model=Page[RepositorySummary])
def list_repositories(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    limit: int | None = Query(default=None, ge=1),
) -> Page[RepositorySummary]:
    """List connected repositories, most recently synced first.

    Never-synced repos sort last, so a freshly connected one does not jump to the top.
    """
    applied = clamp_limit(limit)
    offset = (page - 1) * applied

    total = db.scalar(select(func.count()).select_from(Repository)) or 0
    rows = db.scalars(
        select(Repository)
        .order_by(
            # Synced repos first, never-synced last — a freshly connected repo must not
            # jump to the top of the list before it has any data to show.
            asc(Repository.last_synced_at.is_(None)),
            desc(Repository.last_synced_at),
            desc(Repository.id),
        )
        .offset(offset)
        .limit(applied)
    ).all()

    return Page(
        items=[RepositorySummary.model_validate(row) for row in rows],
        page=page,
        limit=applied,
        total=total,
    )


@router.get("/{repository_id}", response_model=RepositoryDetail)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
) -> RepositoryDetail:
    """One repository with its latest ingestion job. 404 when the repository is unknown."""
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise HTTPProblem(status.HTTP_404_NOT_FOUND, f"Repository {repository_id} not found.")

    latest_job = db.scalars(
        select(IngestionJob)
        .where(IngestionJob.repository_id == repository_id)
        .order_by(desc(IngestionJob.id))
    ).first()

    detail = RepositoryDetail.model_validate(repository)
    if latest_job is not None:
        detail.latest_job = LatestJobSummary.model_validate(latest_job)
    return detail
