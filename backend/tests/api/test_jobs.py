"""`GET /api/v1/jobs/{job_id}` contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import IngestionJob, Repository
from tests.api.conftest import make_settings


def _make_job(db_session: Session, **overrides: object) -> IngestionJob:
    repository = Repository(owner="acme", name="widgets", full_name="acme/widgets")
    db_session.add(repository)
    db_session.commit()

    fields: dict[str, object] = {
        "repository_id": repository.id,
        "status": "succeeded",
        "started_at": datetime.now(UTC) - timedelta(hours=1),
        "finished_at": datetime.now(UTC),
        "counts": {"prs": 42, "issues": 7, "commits": 331, "releases": 5, "api_calls": 12},
        "cursor": {"phase": "done", "cursors": {}, "mode": "full", "history_months": 24},
    }
    fields.update(overrides)
    job = IngestionJob(**fields)  # type: ignore[arg-type]
    db_session.add(job)
    db_session.commit()
    return job


class TestGetJob:
    def test_unknown_job_is_a_404(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.get("/api/v1/jobs/42")
        assert response.status_code == 404
        assert response.json() == {
            "status": 404,
            "title": "Not Found",
            "detail": "Ingestion job 42 not found.",
        }

    def test_fields_and_timestamps(self, make_client: object, db_session: Session) -> None:
        job = _make_job(db_session)
        client = make_client(settings=make_settings())
        body = client.get(f"/api/v1/jobs/{job.id}").json()

        assert body["id"] == job.id
        assert body["repository_id"] == job.repository_id
        assert body["status"] == "succeeded"
        assert body["counts"]["prs"] == 42
        assert body["cursor"]["phase"] == "done"
        assert body["error"] is None
        assert body["resume_after"] is None
        # Timestamps carry a timezone offset (docs/api.md).
        assert body["started_at"].endswith(("+00:00", "Z"))
        assert body["finished_at"] is not None

    def test_a_paused_job_exposes_its_resume_time(
        self, make_client: object, db_session: Session
    ) -> None:
        job = _make_job(
            db_session,
            status="paused",
            finished_at=None,
            resume_after=datetime.now(UTC) + timedelta(minutes=30),
            cursor={
                "phase": "pull_requests",
                "cursors": {"pull_requests": "cursor-1"},
                "mode": "full",
                "history_months": 24,
            },
        )
        client = make_client(settings=make_settings())
        body = client.get(f"/api/v1/jobs/{job.id}").json()

        assert body["status"] == "paused"
        assert body["resume_after"] is not None
        # The cursor pins exactly where the job stopped, not at the start.
        assert body["cursor"]["phase"] == "pull_requests"
        assert body["cursor"]["cursors"]["pull_requests"] == "cursor-1"

    def test_a_failed_job_exposes_its_message(
        self, make_client: object, db_session: Session
    ) -> None:
        job = _make_job(db_session, status="failed", error="GitHub returned 404 for acme/widgets")
        client = make_client(settings=make_settings())
        body = client.get(f"/api/v1/jobs/{job.id}").json()

        assert body["status"] == "failed"
        assert body["error"] == "GitHub returned 404 for acme/widgets"
