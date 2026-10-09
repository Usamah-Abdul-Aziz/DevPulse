"""Pipeline tests against the fake GitHub client.

These three tests are the Phase 2 acceptance criteria from `docs/roadmap.md`:

1. **idempotent re-run** — the same pages twice → the same counts, rows updated in place;
2. **resume after a rate-limit stop** — pause mid-run, resume, and it finishes;
3. **bots and generated files flagged** — `is_bot` / `is_generated` set, rows kept.

Plus the windowing behaviour that makes incremental sync cheap (ADR-008) and the large-repo
reduction (ADR-006).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.errors import RateLimitExhausted
from app.ingestion.pipeline import IngestionCursor
from app.models import (
    Commit,
    Contributor,
    FileChange,
    Issue,
    PullRequest,
    PullRequestReview,
    Release,
    Repository,
)
from tests.ingestion.conftest import make_repository, make_settings, run_pipeline
from tests.ingestion.fake_github import (
    FakeGitHubClient,
    commit_node,
    iso,
    issue_node,
    now,
    pr_node,
)

_WINDOW_START = now() - timedelta(days=720)


@pytest.fixture()
def repository(db_session: Session) -> Repository:
    return make_repository(db_session)


def _two_pr_pages() -> list[list[dict]]:
    return [
        [
            pr_node(1, updated=now() - timedelta(days=1)),
            pr_node(2, updated=now() - timedelta(days=2)),
        ],
        [pr_node(3, updated=now() - timedelta(days=3))],
    ]


class TestPhasesWriteRows:
    def test_every_entity_is_loaded(self, db_session: Session, repository: Repository) -> None:
        client = FakeGitHubClient(
            pr_pages=[[pr_node(1, updated=now())]],
            issue_pages=[[issue_node(1, updated=now())]],
            commit_pages=[[commit_node("a" * 40, committed=now())]],
            releases=[
                {
                    "tag_name": "v1.0.0",
                    "name": "First",
                    "published_at": iso(now()),
                    "author": {"node_id": "U_1", "login": "octocat"},
                }
            ],
        )

        pipeline, cursor = run_pipeline(db_session, client, repository)

        assert cursor.phase == "done"
        assert pipeline.counts["prs"] == 1
        assert pipeline.counts["reviews"] == 1
        assert pipeline.counts["issues"] == 1
        assert pipeline.counts["commits"] == 1
        assert pipeline.counts["releases"] == 1
        assert pipeline.counts["files"] == 1

        assert db_session.scalar(select(func.count(PullRequest.id))) == 1
        assert db_session.scalar(select(func.count(Issue.id))) == 1
        assert db_session.scalar(select(func.count(Commit.id))) == 1
        assert db_session.scalar(select(func.count(Release.id))) == 1
        assert db_session.scalar(select(func.count(PullRequestReview.id))) == 1

    def test_default_branch_is_stored(self, db_session: Session) -> None:
        repository = make_repository(db_session)
        client = FakeGitHubClient(
            repo={
                "repository": {
                    "defaultBranchRef": {"name": "develop"},
                    "pullRequests": {"totalCount": 0},
                }
            }
        )
        run_pipeline(db_session, client, repository)
        assert repository.default_branch == "develop"


class TestIdempotency:
    """Acceptance criterion 1: re-ingesting the same pages must not duplicate rows."""

    def test_re_running_the_same_pages_is_a_no_op(
        self, db_session: Session, repository: object
    ) -> None:
        pages = _two_pr_pages()
        client = FakeGitHubClient(pr_pages=pages, issue_pages=[], commit_pages=[])

        first, _ = run_pipeline(db_session, client, repository)
        first_rows = db_session.scalar(select(func.count(PullRequest.id)))
        first_files = db_session.scalar(select(func.count(FileChange.id)))

        # A fresh client with the same pages — exactly what a re-sync looks like.
        client = FakeGitHubClient(pr_pages=pages, issue_pages=[], commit_pages=[])
        second, _ = run_pipeline(db_session, client, repository)

        assert second.counts["prs"] == first.counts["prs"] == 3
        assert db_session.scalar(select(func.count(PullRequest.id))) == first_rows == 3
        assert db_session.scalar(select(func.count(FileChange.id))) == first_files
        # Idempotent upserts update in place: ids are stable across runs.
        numbers = sorted(db_session.scalars(select(PullRequest.number)).all())
        assert numbers == [1, 2, 3]

    def test_updated_pr_fields_are_refreshed(self, db_session: Session, repository: object) -> None:
        pages = [[pr_node(1, updated=now(), title="Original")]]
        run_pipeline(db_session, FakeGitHubClient(pr_pages=pages), repository)

        pages = [[pr_node(1, updated=now(), title="Retitled", state="CLOSED")]]
        run_pipeline(db_session, FakeGitHubClient(pr_pages=pages), repository)

        pr = db_session.scalars(select(PullRequest)).one()
        assert pr.title == "Retitled"
        assert pr.state == "CLOSED"

    def test_contributors_are_keyed_by_github_id_not_login(
        self, db_session: Session, repository: object
    ) -> None:
        # Same person, two different logins across two syncs: one contributor row.
        pages = [[pr_node(1, updated=now(), author="octocat", author_id="U_1")]]
        run_pipeline(db_session, FakeGitHubClient(pr_pages=pages), repository)
        pages = [[pr_node(1, updated=now(), author="octocat-renamed", author_id="U_1")]]
        run_pipeline(db_session, FakeGitHubClient(pr_pages=pages), repository)

        contributors = db_session.scalars(
            select(Contributor).where(Contributor.github_id == "U_1")
        ).all()
        assert len(contributors) == 1
        assert contributors[0].login == "octocat-renamed"


class TestResume:
    """Acceptance criterion 2: a paused job resumes from the next page, not the phase start."""

    def test_pausing_mid_phase_then_resuming(self, db_session: Session, repository: object) -> None:
        client = FakeGitHubClient(
            pr_pages=_two_pr_pages(),
            issue_pages=[[issue_node(1, updated=now())]],
            commit_pages=[[commit_node("a" * 40, committed=now())]],
        )
        # The repository call is call 1; the first PR page is call 2. Stop right after it.
        client.exhaust_rate_limit_after(2)

        with pytest.raises(RateLimitExhausted):
            run_pipeline(db_session, client, repository)

        prs_after_pause = db_session.scalar(select(func.count(PullRequest.id)))
        assert prs_after_pause == 2  # page 1 landed, page 2 did not

        # The cursor was recorded mid-phase, pointing at the page we have not read.
        assert client.calls[-1][0] == "fetch_pull_requests"
        cursor = IngestionCursor(
            {
                "phase": "pull_requests",
                "cursors": {"pull_requests": "cursor-1"},
                "window_start": iso(_WINDOW_START),
                "window_end": iso(now()),
                "mode": "full",
            }
        )

        _, returned = run_pipeline(db_session, client, repository, cursor=cursor)

        assert returned.phase == "done"
        assert db_session.scalar(select(func.count(PullRequest.id))) == 3
        # The resumed run did not re-fetch page 1: it started from `cursor-1`.
        pr_fetches = [call for call in client.calls if call[0] == "fetch_pull_requests"]
        afters = [call[1]["after"] for call in pr_fetches]
        assert afters[0] is None and "cursor-1" in afters
        assert db_session.scalar(select(func.count(Issue.id))) == 1
        assert db_session.scalar(select(func.count(Commit.id))) == 1


class TestWindowing:
    def test_pages_stop_at_the_watermark(self, db_session: Session, repository: Repository) -> None:
        # Page 1 is recent, page 2 straddles the 24-month boundary, page 3 is far older.
        # Paging must stop after page 2: reading further would be pure cost.
        client = FakeGitHubClient(
            pr_pages=[
                [pr_node(1, updated=now() - timedelta(days=10))],
                [pr_node(2, updated=now() - timedelta(days=900))],
                [pr_node(3, updated=now() - timedelta(days=1200))],
            ]
        )
        pipeline, _ = run_pipeline(db_session, client, repository)

        assert pipeline.counts["prs"] == 2
        pr_fetches = [call for call in client.calls if call[0] == "fetch_pull_requests"]
        assert len(pr_fetches) == 2  # page 3 was never requested

    def test_the_straddling_page_is_stored(
        self, db_session: Session, repository: Repository
    ) -> None:
        # A page that mixes in-window and out-of-window items is kept in full. Dropping it would
        # lose recently-updated old PRs on an incremental run, which is a silent data hole.
        client = FakeGitHubClient(
            pr_pages=[
                [
                    pr_node(
                        1, updated=now() - timedelta(days=1), created=now() - timedelta(days=400)
                    ),
                    pr_node(
                        2, updated=now() - timedelta(days=800), created=now() - timedelta(days=900)
                    ),
                ]
            ]
        )
        pipeline, _ = run_pipeline(db_session, client, repository)
        assert pipeline.counts["prs"] == 2

    def test_incremental_sync_uses_last_synced_at(
        self, db_session: Session, repository: Repository
    ) -> None:
        # Three pages, newest first. Page 1 straddles a one-day-old watermark; page 3 straddles
        # the 24-month window start. An incremental run stops after page 1.
        pages = [
            [
                pr_node(1, updated=now() - timedelta(hours=2)),
                pr_node(2, updated=now() - timedelta(days=10)),
            ],
            [pr_node(3, updated=now() - timedelta(days=5))],
            [pr_node(4, updated=now() - timedelta(days=800))],
        ]

        repository.last_synced_at = now() - timedelta(days=1)
        client = FakeGitHubClient(pr_pages=pages)
        pipeline, _ = run_pipeline(db_session, client, repository)

        assert pipeline.counts["prs"] == 2
        assert len([call for call in client.calls if call[0] == "fetch_pull_requests"]) == 1

    def test_full_sync_pages_to_the_window_start(
        self, db_session: Session, repository: Repository
    ) -> None:
        # The same pages with no prior sync: the watermark is the 24-month window start, so the
        # run reads until page 3 crosses it. This is the contrast that makes the watermark
        # observable rather than an internal detail.
        pages = [
            [
                pr_node(1, updated=now() - timedelta(hours=2)),
                pr_node(2, updated=now() - timedelta(days=10)),
            ],
            [pr_node(3, updated=now() - timedelta(days=5))],
            [pr_node(4, updated=now() - timedelta(days=800))],
        ]
        pipeline, _ = run_pipeline(db_session, FakeGitHubClient(pr_pages=pages), repository)
        assert pipeline.counts["prs"] == 4

    def test_commits_are_windowed_server_side(
        self, db_session: Session, repository: object
    ) -> None:
        client = FakeGitHubClient(commit_pages=[[commit_node("a" * 40, committed=now())]])
        _, _ = run_pipeline(db_session, client, repository)

        commit_call = next(call for call in client.calls if call[0] == "fetch_commits")
        assert commit_call[1]["since"] is not None
        assert commit_call[1]["until"] is not None

    def test_commits_are_skipped_without_a_default_branch(self, db_session: Session) -> None:
        repository = make_repository(db_session)
        repository.default_branch = None
        client = FakeGitHubClient(commit_pages=[[commit_node("a" * 40, committed=now())]])
        # Start past the repository phase, which would otherwise repopulate the branch.
        cursor = IngestionCursor({"phase": "commits"})
        pipeline, _ = run_pipeline(db_session, client, repository, cursor=cursor)
        assert pipeline.counts["commits"] == 0
        assert not any(call[0] == "fetch_commits" for call in client.calls)

    def test_large_repo_gets_a_reduced_window(
        self, db_session: Session, repository: object
    ) -> None:
        client = FakeGitHubClient(
            repo={
                "repository": {
                    "defaultBranchRef": {"name": "main"},
                    "pullRequests": {"totalCount": 60_000},
                }
            }
        )
        settings = make_settings(ingestion_history_months=24)
        _, cursor = run_pipeline(db_session, client, repository, settings=settings)

        assert cursor.history_months == 12
        months_back = (cursor.window_end - cursor.window_start).days / 30.5
        assert 11.5 <= months_back <= 12.5

    def test_incremental_mode_is_never_shrunk(
        self, db_session: Session, repository: object
    ) -> None:
        # The reduction is a full-sync approximation; an incremental run keeps its window.
        client = FakeGitHubClient(
            repo={
                "repository": {
                    "defaultBranchRef": {"name": "main"},
                    "pullRequests": {"totalCount": 60_000},
                }
            }
        )
        cursor = IngestionCursor({"phase": "repository", "mode": "incremental"})
        settings = make_settings(ingestion_history_months=24)
        _, returned = run_pipeline(db_session, client, repository, settings=settings, cursor=cursor)
        assert returned.history_months != 12


class TestCleaningFlags:
    """Acceptance criterion 3: bots and generated files are flagged, not dropped."""

    def test_bot_authors_are_flagged(self, db_session: Session, repository: object) -> None:
        client = FakeGitHubClient(
            pr_pages=[[pr_node(1, updated=now(), author="dependabot[bot]", author_id="B_1")]]
        )
        run_pipeline(db_session, client, repository)

        bot = db_session.scalars(select(Contributor).where(Contributor.github_id == "B_1")).one()
        assert bot.is_bot is True
        assert bot.is_ghost is False
        # The PR is still stored — flagged, not deleted.
        assert db_session.scalar(select(func.count(PullRequest.id))) == 1

    def test_generated_paths_are_flagged(self, db_session: Session, repository: object) -> None:
        client = FakeGitHubClient(
            pr_pages=[
                [
                    pr_node(
                        1,
                        updated=now(),
                        files=[
                            {"path": "src/main.py", "additions": 5, "deletions": 1},
                            {"path": "package-lock.json", "additions": 900, "deletions": 0},
                        ],
                    )
                ]
            ]
        )
        run_pipeline(db_session, client, repository)

        flags = {row.path: row.is_generated for row in db_session.scalars(select(FileChange)).all()}
        assert flags["src/main.py"] is False
        assert flags["package-lock.json"] is True

    def test_ghost_author_of_a_pr_stays_null(self, db_session: Session, repository: object) -> None:
        node = pr_node(1, updated=now())
        node["author"] = None  # a deleted account: GitHub no longer knows who this was
        run_pipeline(db_session, FakeGitHubClient(pr_pages=[[node]]), repository)

        pr = db_session.scalars(select(PullRequest)).one()
        assert pr.author_id is None
        # The PR itself survives with its raw payload intact (ADR-010).
        assert pr.raw_payload is not None
        assert pr.raw_payload["number"] == 1

    def test_commits_without_a_linked_user_become_ghosts(
        self, db_session: Session, repository: object
    ) -> None:
        node = commit_node(
            "a" * 40, committed=now(), author_login=None, name="Nomad", email="nomad@example.com"
        )
        run_pipeline(db_session, FakeGitHubClient(commit_pages=[[node]]), repository)

        commit = db_session.scalars(select(Commit)).one()
        assert commit.author_name == "Nomad"
        assert commit.author_email == "nomad@example.com"
        # Attributed to the ghost stand-in, never to a real person.
        ghost = db_session.scalars(select(Contributor).where(Contributor.is_ghost.is_(True))).one()
        assert commit.author_id == ghost.id

    def test_pending_reviews_are_not_written(self, db_session: Session, repository: object) -> None:
        node = pr_node(
            1,
            updated=now(),
            reviews=[
                {"id": "R_PENDING", "author": None, "state": "PENDING", "submittedAt": None},
                {
                    "id": "R_APPROVED",
                    "author": {"id": "U_2", "login": "reviewer", "isBot": False},
                    "state": "APPROVED",
                    "submittedAt": iso(now()),
                },
            ],
        )
        pipeline, _ = run_pipeline(db_session, FakeGitHubClient(pr_pages=[[node]]), repository)
        # A pending review is a *request*, not a submitted review (blueprint §6.1).
        assert pipeline.counts["reviews"] == 1
        assert db_session.scalar(select(func.count(PullRequestReview.id))) == 1


class TestTruncation:
    def test_follow_up_file_queries_are_fetched(
        self, db_session: Session, repository: object
    ) -> None:
        # The nested connection holds one file but reports two: the pipeline must fetch the rest.
        node = pr_node(
            1,
            updated=now(),
            files=[{"path": "src/main.py", "additions": 1, "deletions": 0}],
            total_files=2,
        )
        client = FakeGitHubClient(pr_pages=[[node]])
        pipeline, _ = run_pipeline(db_session, client, repository)

        assert pipeline.counts["files"] == 2
        assert any(call[0] == "fetch_pr_files" for call in client.calls)
        pr = db_session.scalars(select(PullRequest)).one()
        assert pr.truncated_files is False

    def test_hitting_the_cap_marks_truncation(
        self, db_session: Session, repository: object
    ) -> None:
        node = pr_node(
            1,
            updated=now(),
            files=[{"path": "src/main.py", "additions": 1, "deletions": 0}],
            total_files=2,
        )
        client = FakeGitHubClient(pr_pages=[[node]])
        settings = make_settings(ingestion_max_file_changes_per_pr=1)

        pipeline, _ = run_pipeline(db_session, client, repository, settings=settings)

        # The cap is hit before any follow-up fetch: the one nested file is all we keep.
        assert pipeline.counts["files"] == 1
        assert not any(call[0] == "fetch_pr_files" for call in client.calls)
        pr = db_session.scalars(select(PullRequest)).one()
        assert pr.truncated_files is True
