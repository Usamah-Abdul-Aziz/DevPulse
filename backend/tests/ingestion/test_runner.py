"""Runner tests: the job state machine, driven end to end through the fake client.

These are the transitions that make resume possible — every one of them is a promise the UI relies
on, and a wrong one turns a rate-limit pause into a stuck or duplicated job.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.ingestion.runner import IngestionRunner, _parse_reset_at
from app.models import IngestionJob, PullRequest, Repository
from tests.ingestion.conftest import make_settings
from tests.ingestion.fake_github import FakeGitHubClient, now, pr_node

_RESET_TIMESTAMP = "1893456000"  # 2030-01-01T00:00:00Z


@pytest.fixture()
def runner_factory(db_session: Session) -> object:
    """Build a runner whose sessions share the test engine, with a stubbed client factory."""

    def _make(*, client: FakeGitHubClient, settings: Settings | None = None) -> IngestionRunner:
        return IngestionRunner(
            sessionmaker(bind=db_session.get_bind()),
            settings=settings or make_settings(),
            client_factory=lambda _settings: client,
        )

    return _make


@pytest.fixture()
def repository(db_session: Session) -> Repository:
    repo = Repository(owner="acme", name="widgets", full_name="acme/widgets", default_branch="main")
    db_session.add(repo)
    db_session.commit()
    return repo


def _make_job(db_session: Session, repository: Repository) -> IngestionJob:
    job = IngestionJob(repository_id=repository.id, status="pending")
    db_session.add(job)
    db_session.commit()
    return job


class TestSuccess:
    def test_succeeded_advances_last_synced_and_records_counts(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        client = FakeGitHubClient(pr_pages=[[pr_node(1, updated=now())]])
        runner: IngestionRunner = runner_factory(client=client)
        job = _make_job(db_session, repository)

        runner(job.id)

        db_session.expire_all()
        reloaded = db_session.get(IngestionJob, job.id)
        assert reloaded.status == "succeeded"
        assert reloaded.error is None
        assert reloaded.resume_after is None
        assert reloaded.counts["prs"] == 1
        assert reloaded.cursor["phase"] == "done"
        assert repository.last_synced_at is not None

    def test_a_resumed_job_is_marked_incremental(
        self, db_session: Session, runner_factory: object
    ) -> None:
        repository = Repository(
            owner="acme",
            name="gadgets",
            full_name="acme/gadgets",
            default_branch="main",
            last_synced_at=datetime.now(UTC) - timedelta(days=3),
        )
        db_session.add(repository)
        db_session.commit()
        job = _make_job(db_session, repository)

        runner: IngestionRunner = runner_factory(client=FakeGitHubClient())
        runner(job.id)

        db_session.expire_all()
        assert db_session.get(IngestionJob, job.id).cursor["mode"] == "incremental"

    def test_a_fresh_job_is_full_mode(self, db_session: Session, runner_factory: object) -> None:
        repository = Repository(
            owner="acme", name="fresh", full_name="acme/fresh", default_branch="main"
        )
        db_session.add(repository)
        db_session.commit()
        job = _make_job(db_session, repository)

        runner: IngestionRunner = runner_factory(client=FakeGitHubClient())
        runner(job.id)

        db_session.expire_all()
        assert db_session.get(IngestionJob, job.id).cursor["mode"] == "full"

    def test_a_missing_job_is_logged_not_raised(self, runner_factory: object) -> None:
        runner: IngestionRunner = runner_factory(client=FakeGitHubClient())
        # No exception: a background task that raises is an unhandled error in the logs.
        runner(999)


class TestPause:
    def test_rate_limit_pauses_with_a_resume_time(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        client = FakeGitHubClient(pr_pages=[[pr_node(1, updated=now())]])
        client.exhaust_rate_limit_after(1)  # the very first page fetch pauses
        runner: IngestionRunner = runner_factory(client=client)
        job = _make_job(db_session, repository)

        runner(job.id)

        db_session.expire_all()
        reloaded = db_session.get(IngestionJob, job.id)
        assert reloaded.status == "paused"
        assert reloaded.error is None
        assert reloaded.resume_after is not None
        # The cursor stops mid-run, which is what makes resume page-granular.
        assert reloaded.cursor["phase"] != "done"

    def test_pausing_does_not_advance_last_synced_at(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        repository.last_synced_at = None
        client = FakeGitHubClient(pr_pages=[[pr_node(1, updated=now())]])
        client.exhaust_rate_limit_after(1)
        runner: IngestionRunner = runner_factory(client=client)

        runner(_make_job(db_session, repository).id)

        assert repository.last_synced_at is None

    def test_resume_completes_the_job(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        # Two PR pages; the fake pauses after the first page exactly once.
        pages = [[pr_node(1, updated=now())], [pr_node(2, updated=now())]]
        client = FakeGitHubClient(pr_pages=pages)
        client.exhaust_rate_limit_after(2)
        runner: IngestionRunner = runner_factory(client=client)
        job = _make_job(db_session, repository)

        runner(job.id)  # pauses

        db_session.expire_all()
        assert db_session.get(IngestionJob, job.id).status == "paused"
        assert db_session.scalar(select(PullRequest.number)) == 1

        runner(job.id)  # resumes from the stored cursor

        db_session.expire_all()
        reloaded = db_session.get(IngestionJob, job.id)
        assert reloaded.status == "succeeded"
        assert sorted(db_session.scalars(select(PullRequest.number)).all()) == [1, 2]
        # The resumed run did not re-read page 1.
        afters = [call[1]["after"] for call in client.calls if call[0] == "fetch_pull_requests"]
        assert afters.count(None) == 1


class TestFailure:
    def test_an_unexpected_error_fails_the_job(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        class BoomClient(FakeGitHubClient):
            def get_repository(self, owner: str, name: str) -> dict:
                raise RuntimeError("the database is on fire")

        runner: IngestionRunner = runner_factory(client=BoomClient())
        job = _make_job(db_session, repository)

        runner(job.id)

        db_session.expire_all()
        reloaded = db_session.get(IngestionJob, job.id)
        assert reloaded.status == "failed"
        assert "the database is on fire" in reloaded.error
        assert reloaded.error is not None and len(reloaded.error) <= 500

    def test_error_messages_are_bounded(
        self, db_session: Session, repository: Repository, runner_factory: object
    ) -> None:
        class VerboseClient(FakeGitHubClient):
            def get_repository(self, owner: str, name: str) -> dict:
                raise RuntimeError("x" * 5000)

        runner: IngestionRunner = runner_factory(client=VerboseClient())
        job = _make_job(db_session, repository)

        runner(job.id)

        db_session.expire_all()
        reloaded = db_session.get(IngestionJob, job.id)
        # Error text is user-facing: never a stack dump, never unbounded.
        assert len(reloaded.error) == 500
        assert "Traceback" not in reloaded.error


class TestParseResetAt:
    def test_a_unix_timestamp_becomes_utc(self) -> None:
        parsed = _parse_reset_at(_RESET_TIMESTAMP)
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.year == 2030

    def test_an_iso_timestamp_is_accepted(self) -> None:
        parsed = _parse_reset_at("2030-01-01T00:00:00Z")
        assert parsed is not None
        assert parsed.year == 2030

    def test_a_naive_iso_timestamp_is_assumed_utc(self) -> None:
        parsed = _parse_reset_at("2030-01-01T00:00:00")
        assert parsed is not None
        assert parsed.tzinfo is not None

    @pytest.mark.parametrize("value", [None, "", "not-a-time"])
    def test_unparseable_input_is_none(self, value: str | None) -> None:
        assert _parse_reset_at(value) is None
