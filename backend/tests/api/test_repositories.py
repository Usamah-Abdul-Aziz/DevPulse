"""`POST /connect`, `GET /repositories`, `GET /repositories/{id}` contracts.

The connect endpoint is the only write path in Phase 2, so its contract is tested closely: every
guard that fails closed, the 202 that means "accepted, not done", and the job-deduplication rules.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import IngestionJob, Repository
from app.schemas.pagination import DEFAULT_LIMIT, MAX_LIMIT
from tests.api.conftest import RecordingRunner, make_settings


def _make_runner(db_session: Session) -> RecordingRunner:
    return RecordingRunner(sessionmaker(bind=db_session.get_bind()))


class TestConnectValidation:
    def test_bad_format_is_a_400(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.post("/api/v1/repositories/connect", json={"repository": "not-a-repo"})
        assert response.status_code == 422
        assert "owner/name" in response.json()["detail"][0]["msg"]

    def test_missing_field_is_a_422(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.post("/api/v1/repositories/connect", json={})
        assert response.status_code == 422

    def test_empty_allow_list_fails_closed(self, make_client: object) -> None:
        """An unset ALLOWED_REPOS must mean 'nothing is allowed', never 'everything is'."""
        client = make_client(settings=make_settings(allowed_repos=[]))
        response = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})

        assert response.status_code == 400
        assert "ALLOWED_REPOS" in response.json()["detail"]
        assert "acme/widgets" not in response.json()["detail"]

    def test_repository_not_in_allow_list_is_a_403(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.post("/api/v1/repositories/connect", json={"repository": "evil/corp"})
        assert response.status_code == 403
        assert "evil/corp" in response.json()["detail"]

    def test_missing_token_is_a_400(self, make_client: object) -> None:
        client = make_client(settings=make_settings(github_token=None))
        response = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        assert response.status_code == 400
        assert "GITHUB_TOKEN" in response.json()["detail"]

    def test_allow_list_is_case_insensitive(self, make_client: object, db_session: Session) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)
        response = client.post("/api/v1/repositories/connect", json={"repository": "ACME/Widgets"})
        assert response.status_code == 202
        assert runner.job_ids == [1]

    def test_url_forms_are_accepted(self, make_client: object, db_session: Session) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        for value in (
            "https://github.com/acme/widgets",
            "https://github.com/acme/widgets.git",
            "acme/widgets/",
        ):
            response = client.post("/api/v1/repositories/connect", json={"repository": value})
            assert response.status_code == 202, value

        # Every form is the same repository; only the first created a row.
        assert db_session.scalar(select(func.count(Repository.id))) == 1
        assert db_session.scalars(select(Repository.full_name)).one() == "acme/widgets"


class TestConnectAcceptance:
    def test_accepted_creates_repository_and_job(
        self, make_client: object, db_session: Session
    ) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        response = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "pending"
        assert set(body) == {"job_id", "repository_id", "status"}

        repository = db_session.scalars(select(Repository)).one()
        assert repository.full_name == "acme/widgets"
        assert repository.id == body["repository_id"]
        assert runner.job_ids == [body["job_id"]]

    def test_a_running_job_is_returned_not_duplicated(
        self, make_client: object, db_session: Session
    ) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        first = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        second = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})

        assert first.json()["job_id"] == second.json()["job_id"]
        assert runner.job_ids == [1]  # the background task ran once, not twice
        assert db_session.scalar(select(func.count()).select_from(Repository)) == 1

    def test_a_terminal_job_starts_a_new_one(
        self, make_client: object, db_session: Session
    ) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        job = db_session.scalars(select(IngestionJob)).one()
        job.status = "succeeded"
        db_session.commit()

        second = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})

        assert second.json()["job_id"] != job.id
        assert len(runner.job_ids) == 2

    def test_a_paused_job_not_yet_due_is_left_alone(
        self, make_client: object, db_session: Session
    ) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        job = db_session.scalars(select(IngestionJob)).one()
        job.status = "paused"
        job.resume_after = datetime.now(UTC) + timedelta(hours=1)
        db_session.commit()

        second = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        assert second.json()["job_id"] == job.id
        assert second.json()["status"] == "paused"
        assert runner.job_ids == [job.id]  # not re-queued

    def test_a_paused_job_that_is_due_is_resumed(
        self, make_client: object, db_session: Session
    ) -> None:
        runner = _make_runner(db_session)
        client = make_client(settings=make_settings(), runner=runner)

        client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        job = db_session.scalars(select(IngestionJob)).one()
        job.status = "paused"
        job.resume_after = datetime.now(UTC) - timedelta(minutes=5)
        db_session.commit()

        second = client.post("/api/v1/repositories/connect", json={"repository": "acme/widgets"})
        assert second.json()["job_id"] == job.id
        assert second.json()["status"] == "pending"
        assert runner.job_ids == [job.id, job.id]  # queued twice: once, then resumed


class TestListRepositories:
    def test_empty_list(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.get("/api/v1/repositories")
        assert response.status_code == 200
        assert response.json() == {"items": [], "page": 1, "limit": DEFAULT_LIMIT, "total": 0}

    def test_envelope_and_ordering(self, make_client: object, db_session: Session) -> None:
        old = Repository(owner="acme", name="old", full_name="acme/old")
        new = Repository(
            owner="acme",
            name="new",
            full_name="acme/new",
            last_synced_at=datetime.now(UTC),
        )
        db_session.add_all([old, new])
        db_session.commit()

        client = make_client(settings=make_settings())
        body = client.get("/api/v1/repositories").json()

        assert [item["full_name"] for item in body["items"]] == ["acme/new", "acme/old"]
        assert body["total"] == 2
        assert body["page"] == 1

    def test_pagination_params(self, make_client: object, db_session: Session) -> None:
        for index in range(5):
            db_session.add(
                Repository(owner="acme", name=f"repo-{index}", full_name=f"acme/repo-{index}")
            )
        db_session.commit()

        client = make_client(settings=make_settings())
        body = client.get("/api/v1/repositories?page=2&limit=2").json()
        assert body["page"] == 2
        assert body["limit"] == 2
        assert len(body["items"]) == 2
        assert body["total"] == 5

    def test_limit_is_clamped_to_the_maximum(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        body = client.get("/api/v1/repositories?limit=1000").json()
        assert body["limit"] == MAX_LIMIT


class TestRepositoryDetail:
    def test_unknown_id_is_a_404(self, make_client: object) -> None:
        client = make_client(settings=make_settings())
        response = client.get("/api/v1/repositories/42")
        assert response.status_code == 404
        assert response.json() == {
            "status": 404,
            "title": "Not Found",
            "detail": "Repository 42 not found.",
        }

    def test_detail_includes_the_latest_job(self, make_client: object, db_session: Session) -> None:
        repository = Repository(owner="acme", name="widgets", full_name="acme/widgets")
        db_session.add(repository)
        db_session.commit()
        db_session.add(
            IngestionJob(
                repository_id=repository.id,
                status="succeeded",
                counts={"prs": 7},
                started_at=datetime.now(UTC) - timedelta(hours=1),
                finished_at=datetime.now(UTC),
            )
        )
        db_session.commit()

        client = make_client(settings=make_settings())
        body = client.get(f"/api/v1/repositories/{repository.id}").json()

        assert body["full_name"] == "acme/widgets"
        assert body["latest_job"]["status"] == "succeeded"
        assert body["latest_job"]["counts"] == {"prs": 7}

    def test_detail_without_any_job(self, make_client: object, db_session: Session) -> None:
        repository = Repository(owner="acme", name="widgets", full_name="acme/widgets")
        db_session.add(repository)
        db_session.commit()

        client = make_client(settings=make_settings())
        body = client.get(f"/api/v1/repositories/{repository.id}").json()
        assert body["latest_job"] is None
