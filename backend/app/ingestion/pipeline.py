"""Ingestion pipeline: phase orchestration with page-granular resume.

Phases run in dependency order:

    repository → pull_requests → issues → commits → releases → done

The cursor is persisted after every fetched page, so a job that stops mid-phase resumes from the
next page rather than redoing the phase. Pausing is deliberate: when the rate budget runs low the
pipeline raises `RateLimitExhausted`, the runner marks the job `paused` with `resume_after` set to
GitHub's reset time, and the next run continues exactly where it stopped.

Paging without `since` (ADR-008): PRs and issues page `UPDATED_AT DESC` and stop when the oldest
item on a page predates the watermark. That makes incremental sync read only what changed, and
full sync read only the configured window. Commits filter server-side with `since`/`until`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.dates import as_utc
from app.ingestion.github_client import GitHubClient
from app.ingestion.loaders import (
    ContributorResolver,
    load_commits,
    load_issues,
    load_pr_files,
    load_pull_requests,
    load_releases,
)
from app.models import Repository

log = logging.getLogger(__name__)

#: Ordered phase names; the cursor stores the current one.
PHASES: tuple[str, ...] = (
    "repository",
    "pull_requests",
    "issues",
    "commits",
    "releases",
    "done",
)

#: Repositories above this all-time PR count get a reduced window (ADR-006).
LARGE_REPO_PR_THRESHOLD = 50_000
REDUCED_HISTORY_MONTHS = 12

_MAX_PAGES_PER_PHASE = 2_000


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class IngestionCursor:
    """JSON-serializable resume state, written to `ingestion_jobs.cursor` after every page."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.phase: str = data.get("phase", PHASES[0])
        self.cursors: dict[str, str | None] = data.get("cursors", {})
        self.window_start: datetime | None = self._dt(data.get("window_start"))
        self.window_end: datetime | None = self._dt(data.get("window_end"))
        self.history_months: int = data.get("history_months", 0)
        self.mode: str = data.get("mode", "full")

    @staticmethod
    def _dt(value: str | None) -> datetime | None:
        return _parse(value) if value else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "cursors": self.cursors,
            "window_start": _iso(self.window_start) if self.window_start else None,
            "window_end": _iso(self.window_end) if self.window_end else None,
            "history_months": self.history_months,
            "mode": self.mode,
        }


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return as_utc(dt)


class IngestionPipeline:
    """Runs one ingestion job to completion or until the rate budget pauses it."""

    def __init__(
        self,
        session: Session,
        client: GitHubClient,
        repository: Repository,
        *,
        settings: Settings | None = None,
        cursor: IngestionCursor | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.repository = repository
        self.settings = settings or get_settings()
        self.cursor = cursor or IngestionCursor()
        self.counts: dict[str, int] = {
            "prs": 0,
            "reviews": 0,
            "issues": 0,
            "commits": 0,
            "files": 0,
            "releases": 0,
            "contributors": 0,
            "api_calls": 0,
        }

    # -- public ---------------------------------------------------------------

    def run(self) -> IngestionCursor:
        """Execute phases from the cursor's position. Raises `RateLimitExhausted` to pause."""
        if self.cursor.window_end is None:
            self.cursor.window_end = _now()
        if self.cursor.window_start is None:
            months = self.settings.ingestion_history_months
            self.cursor.window_start = self.cursor.window_end - timedelta(days=30.5 * months)
            self.cursor.history_months = months
            # `mode` is set by the caller: "full" by default, "incremental" when the runner sees a
            # repository that has synced before. The window is still 24 months either way — what
            # changes is the watermark, which is `last_synced_at` for an incremental run.

        phase_index = PHASES.index(self.cursor.phase) if self.cursor.phase in PHASES else 0
        for phase in PHASES[phase_index:]:
            self.cursor.phase = phase
            method = getattr(self, f"_phase_{phase}", None)
            if method is None:
                continue
            method()
            self.cursor.cursors.pop(phase, None)

        self.cursor.phase = "done"
        return self.cursor

    # -- phases ---------------------------------------------------------------

    def _phase_repository(self) -> None:
        """Fetch repo metadata; shrink the window for very large repos (ADR-006)."""
        data = self.client.get_repository(self.repository.owner, self.repository.name)
        self.counts["api_calls"] += 1
        repo_node = data.get("repository") or {}
        branch = (repo_node.get("defaultBranchRef") or {}).get("name")
        if branch:
            self.repository.default_branch = branch

        total_prs = (repo_node.get("pullRequests") or {}).get("totalCount", 0)
        if total_prs > LARGE_REPO_PR_THRESHOLD and self.cursor.mode == "full":
            log.info(
                "%s has %d PRs; reducing window from %d to %d months",
                self.repository.full_name,
                total_prs,
                self.cursor.history_months,
                REDUCED_HISTORY_MONTHS,
            )
            self.cursor.window_start = self.cursor.window_end - timedelta(
                days=30.5 * REDUCED_HISTORY_MONTHS
            )
            self.cursor.history_months = REDUCED_HISTORY_MONTHS
            self.cursor.cursors["_large_repo_prs"] = str(total_prs)
            self._persist()

    def _phase_pull_requests(self) -> None:
        resolver = ContributorResolver(self.session, self.repository.id)
        watermark = self._watermark()

        for _ in range(_MAX_PAGES_PER_PHASE):
            after = self.cursor.cursors.get("pull_requests")
            data = self.client.fetch_pull_requests(
                self.repository.owner,
                self.repository.name,
                first=self.settings.ingestion_page_size,
                after=after,
            )
            self.counts["api_calls"] += 1

            connection = (data.get("repository") or {}).get("pullRequests") or {}
            nodes = connection.get("nodes") or []
            page_info = connection.get("pageInfo") or {}
            self.cursor.cursors["pull_requests"] = (
                page_info.get("endCursor") if page_info.get("hasNextPage") else None
            )

            if nodes:
                self._load_pr_page(nodes, resolver)
            self._persist()

            # Stop when the oldest item on the page predates the watermark.
            oldest = min((_parse(n.get("updatedAt")) or _now()) for n in nodes) if nodes else None
            if not page_info.get("hasNextPage") or (oldest is not None and oldest < watermark):
                break

    def _load_pr_page(self, nodes: list[dict[str, Any]], resolver: ContributorResolver) -> None:
        prs, reviews = load_pull_requests(
            self.session, self.repository.id, nodes, resolver=resolver
        )
        self.counts["prs"] += prs
        self.counts["reviews"] += reviews

        for node in nodes:
            files_conn = node.get("files") or {}
            file_nodes = files_conn.get("nodes") or []
            pr_id = self._pr_id(node["number"])
            if pr_id is None:
                continue

            self.counts["files"] += load_pr_files(self.session, pr_id, file_nodes, truncated=False)

            # Nested connections cap at 100; fetch the rest up to the configured cap.
            total = files_conn.get("totalCount") or len(file_nodes)
            if total > len(file_nodes):
                self.counts["files"] += self._fetch_remaining_pr_files(
                    node["number"], pr_id, len(file_nodes), total
                )

    def _fetch_remaining_pr_files(self, number: int, pr_id: int, have: int, total: int) -> int:
        """Page a PR's file connection past the nested 100-item cap (ADR-006 truncation)."""
        cap = self.settings.ingestion_max_file_changes_per_pr
        if have >= cap:
            self._mark_truncated(number)
            return 0

        written = 0
        after: str | None = None
        while have < cap:
            data = self.client.fetch_pr_files(
                self.repository.owner,
                self.repository.name,
                number,
                first=min(self.settings.ingestion_page_size, cap - have),
                after=after,
            )
            self.counts["api_calls"] += 1
            connection = ((data.get("repository") or {}).get("pullRequest") or {}).get(
                "files"
            ) or {}
            nodes = connection.get("nodes") or []
            page_info = connection.get("pageInfo") or {}

            written += load_pr_files(self.session, pr_id, nodes, truncated=False)
            have += len(nodes)

            if not page_info.get("hasNextPage") or not nodes:
                break
            after = page_info.get("endCursor")

        if have < total:
            self._mark_truncated(number)
        return written

    def _mark_truncated(self, number: int) -> None:
        from sqlalchemy import select

        from app.models import PullRequest

        pr = self.session.scalars(
            select(PullRequest).where(
                PullRequest.repository_id == self.repository.id,
                PullRequest.number == number,
            )
        ).one_or_none()
        if pr is not None:
            pr.truncated_files = True

    def _pr_id(self, number: int) -> int | None:
        from sqlalchemy import select

        from app.models import PullRequest

        pr = self.session.scalars(
            select(PullRequest).where(
                PullRequest.repository_id == self.repository.id,
                PullRequest.number == number,
            )
        ).one_or_none()
        return pr.id if pr else None

    def _phase_issues(self) -> None:
        resolver = ContributorResolver(self.session, self.repository.id)
        watermark = self._watermark()

        for _ in range(_MAX_PAGES_PER_PHASE):
            after = self.cursor.cursors.get("issues")
            data = self.client.fetch_issues(
                self.repository.owner,
                self.repository.name,
                first=self.settings.ingestion_page_size,
                after=after,
            )
            self.counts["api_calls"] += 1

            connection = (data.get("repository") or {}).get("issues") or {}
            nodes = connection.get("nodes") or []
            page_info = connection.get("pageInfo") or {}
            self.cursor.cursors["issues"] = (
                page_info.get("endCursor") if page_info.get("hasNextPage") else None
            )

            if nodes:
                self.counts["issues"] += load_issues(
                    self.session, self.repository.id, nodes, resolver=resolver
                )
            self._persist()

            oldest = min((_parse(n.get("updatedAt")) or _now()) for n in nodes) if nodes else None
            if not page_info.get("hasNextPage") or (oldest is not None and oldest < watermark):
                break

    def _phase_commits(self) -> None:
        """Commits use server-side `since`/`until` — `history` supports them, unlike PRs/issues."""
        branch = self.repository.default_branch
        if not branch:
            log.warning(
                "No default branch known for %s; skipping commits", self.repository.full_name
            )
            return

        resolver = ContributorResolver(self.session, self.repository.id)

        for _ in range(_MAX_PAGES_PER_PHASE):
            after = self.cursor.cursors.get("commits")
            data = self.client.fetch_commits(
                self.repository.owner,
                self.repository.name,
                branch,
                first=self.settings.ingestion_page_size,
                after=after,
                since=_iso(self.cursor.window_start) if self.cursor.window_start else None,
                until=_iso(self.cursor.window_end) if self.cursor.window_end else None,
            )
            self.counts["api_calls"] += 1

            ref = (data.get("repository") or {}).get("ref") or {}
            history = ((ref.get("target") or {}).get("history")) or {}
            nodes = history.get("nodes") or []
            page_info = history.get("pageInfo") or {}
            self.cursor.cursors["commits"] = (
                page_info.get("endCursor") if page_info.get("hasNextPage") else None
            )

            if nodes:
                self.counts["commits"] += load_commits(
                    self.session, self.repository.id, nodes, resolver=resolver
                )
            self._persist()

            if not page_info.get("hasNextPage") or not nodes:
                break

    def _phase_releases(self) -> None:
        resolver = ContributorResolver(self.session, self.repository.id)
        page = 1

        for _ in range(_MAX_PAGES_PER_PHASE):
            per_page = self.settings.ingestion_page_size
            data = self.client.rest(
                f"/repos/{self.repository.owner}/{self.repository.name}/releases",
                params={"per_page": per_page, "page": page},
            )
            self.counts["api_calls"] += 1

            if not isinstance(data, list) or not data:
                break

            self.counts["releases"] += load_releases(
                self.session, self.repository.id, data, resolver=resolver
            )
            self._persist()

            if len(data) < per_page:
                break
            page += 1

    # -- helpers --------------------------------------------------------------

    def _persist(self) -> None:
        """Commit after a page so a crash or restart loses at most one page of progress.

        The runner keeps `ingestion_jobs.cursor` in step with this commit boundary, which is what
        makes resume page-granular rather than phase-granular.
        """
        self.session.commit()

    def _watermark(self) -> datetime:
        """Items updated before this time are out of scope: the window start, or the last sync."""
        assert self.cursor.window_start is not None
        last_synced = self.repository.last_synced_at
        if last_synced is not None and as_utc(last_synced) > self.cursor.window_start:
            return as_utc(last_synced)
        return self.cursor.window_start
