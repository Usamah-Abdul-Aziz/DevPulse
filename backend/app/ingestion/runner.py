"""Job runner: owns one session, drives the pipeline, and records the outcome.

This is the only place that transitions an `ingestion_jobs` row. Keeping the state machine in one
function is what makes the resume contract auditable: a `paused` job always has a cursor and a
`resume_after`, a `failed` job always has a bounded error message, and a `succeeded` job always has
`last_synced_at` advanced.

The runner runs in a FastAPI background task, so it gets its *own* session — never the request's —
and commits per page. That way a crash or a container restart loses at most one page of work.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.ingestion.errors import RateLimitExhausted
from app.ingestion.github_client import GitHubClient
from app.ingestion.pipeline import IngestionCursor, IngestionPipeline
from app.models import IngestionJob

log = logging.getLogger(__name__)

#: Error messages are user-facing; a stack dump would be a leak.
_MAX_ERROR_CHARS = 500


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_reset_at(reset_at: str | None) -> datetime | None:
    """GitHub's reset time, as either a unix timestamp or an ISO timestamp."""
    if not reset_at:
        return None
    try:
        return datetime.fromtimestamp(int(reset_at), tz=UTC)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ClientFactory(Protocol):
    """Builds the GitHub client used by a job. Tests inject a fake."""

    def __call__(self, settings: Settings) -> GitHubClient: ...


def default_client_factory(settings: Settings) -> GitHubClient:
    return GitHubClient(settings=settings)


class IngestionRunner:
    """Runs ingestion jobs. Injected as a dependency so tests can swap in a synchronous one."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        settings: Settings | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.settings = settings or get_settings()
        self._client_factory = client_factory or default_client_factory

    def __call__(self, job_id: int) -> None:
        """Run `job_id` to completion, a pause, or a failure. Safe to call in a background task."""
        session = self._session_factory()
        try:
            self._run(session, job_id)
        finally:
            session.close()

    # -- internals ------------------------------------------------------------

    def _run(self, session: Session, job_id: int) -> None:
        job = session.get(IngestionJob, job_id)
        if job is None:
            log.error("Ingestion job %s not found", job_id)
            return

        repository = job.repository
        if repository is None:
            log.error("Ingestion job %s has no repository", job_id)
            return

        job.status = "running"
        job.started_at = job.started_at or _now()
        job.error = None
        session.commit()

        cursor = IngestionCursor(job.cursor) if job.cursor else IngestionCursor()
        # A resumed job is incremental: only items newer than the last sync are in scope.
        if job.cursor is None and repository.last_synced_at is not None:
            cursor.mode = "incremental"

        counts: dict[str, int] = job.counts or {}
        try:
            with self._client_factory(self.settings) as client:
                pipeline = IngestionPipeline(
                    session,
                    client,
                    repository,
                    settings=self.settings,
                    cursor=cursor,
                )
                # Persist the cursor and running totals after every page, not just at the end.
                pipeline.run()
                counts = pipeline.counts

            repository.last_synced_at = _now()
            job.cursor = cursor.to_dict()
            job.counts = counts
            job.status = "succeeded"
            job.finished_at = _now()
            job.resume_after = None
            session.commit()
            log.info(
                "Ingestion job %s succeeded for %s: %s",
                job_id,
                repository.full_name,
                counts,
            )
        except RateLimitExhausted as exc:
            # Leave the cursor exactly where the pipeline stopped; the next run picks it up.
            job.cursor = cursor.to_dict()
            job.counts = counts
            job.status = "paused"
            job.resume_after = _parse_reset_at(exc.reset_at)
            session.commit()
            log.info(
                "Ingestion job %s paused (rate limit on %s, %s points left); resumes after %s",
                job_id,
                exc.resource,
                exc.remaining,
                job.resume_after,
            )
        except Exception as exc:
            session.rollback()
            job.status = "failed"
            job.error = str(exc)[:_MAX_ERROR_CHARS]
            job.finished_at = _now()
            session.commit()
            log.exception("Ingestion job %s failed", job_id)


def get_ingestion_runner() -> IngestionRunner:
    """FastAPI dependency. Override this in tests to run jobs synchronously."""
    from app.core.database import SessionLocal

    return IngestionRunner(SessionLocal)
