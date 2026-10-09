"""GraphQL node → row conversion, plus contributor resolution.

Contributors are resolved (created if missing) before the entities that reference them, so an FK
never points at a row that does not exist. Resolution is memoized per session: within one job the
same GitHub author maps to one contributor row, which is what keeps re-ingestion idempotent.

Ghost handling (ADR-010): when GitHub returns no `author` (deleted account), the referencing column
stays NULL and the raw login survives in `raw_payload` — the person is not silently invented.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.cleaning import is_bot_login, is_generated_path
from app.ingestion.db import bulk_upsert
from app.models import (
    GHOST_GITHUB_ID,
    Commit,
    Contributor,
    FileChange,
    Issue,
    PullRequest,
    PullRequestReview,
    Release,
)

log = logging.getLogger(__name__)

#: Fields refreshed on re-ingestion of an existing PR row.
_PR_UPDATE_COLS = (
    "title",
    "state",
    "author_id",
    "updated_at",
    "closed_at",
    "merged_at",
    "is_draft",
    "additions",
    "deletions",
    "changed_files",
    "base_branch",
    "head_branch",
    "labels",
    "truncated_files",
    "raw_payload",
)

#: Labels that are pure GitHub housekeeping and carry no analytic meaning.
_DROP_LABELS = frozenset({"wip", "do-not-merge", "stale", "good first issue", "help wanted"})


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp into a timezone-aware datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ContributorResolver:
    """Maps GitHub author nodes to `contributors` rows, memoized per session."""

    def __init__(self, session: Session, repository_id: int) -> None:
        self.session = session
        self.repository_id = repository_id
        self._cache: dict[str, Contributor | None] = {}

    def resolve(self, author: dict[str, Any] | None) -> Contributor | None:
        """Return the contributor for an `author` node, creating it if necessary.

        `None` means GitHub no longer knows the author (deleted account): we record nothing and
        let the caller store a NULL foreign key, preserving the raw login in `raw_payload`.
        """
        if author is None:
            return None

        github_id = author.get("id")
        if github_id is None:
            return None

        if github_id in self._cache:
            return self._cache[github_id]

        contributor = self.session.scalars(
            select(Contributor).where(
                Contributor.repository_id == self.repository_id,
                Contributor.github_id == github_id,
            )
        ).one_or_none()

        if contributor is None:
            login = author.get("login")
            contributor = Contributor(
                repository_id=self.repository_id,
                github_id=github_id,
                login=login,
                is_bot=bool(author.get("isBot")) or is_bot_login(login),
                is_ghost=github_id == GHOST_GITHUB_ID,
            )
            self.session.add(contributor)
            self.session.flush()
        else:
            # GitHub logins are mutable; the node id is the stable key. Refresh a renamed login so
            # the UI never shows a handle GitHub stopped answering to (ADR-010).
            login = author.get("login")
            if login and login != contributor.login:
                contributor.login = login

        self._cache[github_id] = contributor
        return contributor

    def resolve_ghost(self, name: str | None, email: str | None) -> Contributor | None:
        """Get-or-create the repository's single ghost contributor (deleted-account stand-in).

        Used for commits whose git author has no linked GitHub user: the commit still happened and
        must be attributable *somehow*, but it must not be attributed to a real person.
        """
        if GHOST_GITHUB_ID in self._cache:
            return self._cache[GHOST_GITHUB_ID]

        contributor = self.session.scalars(
            select(Contributor).where(
                Contributor.repository_id == self.repository_id,
                Contributor.github_id == GHOST_GITHUB_ID,
            )
        ).one_or_none()

        if contributor is None:
            contributor = Contributor(
                repository_id=self.repository_id,
                github_id=GHOST_GITHUB_ID,
                login="ghost",
                name=name,
                email=email,
                is_ghost=True,
            )
            self.session.add(contributor)
            self.session.flush()

        self._cache[GHOST_GITHUB_ID] = contributor
        return contributor


def _labels(node_labels: dict[str, Any] | None) -> list[str] | None:
    if not node_labels:
        return None
    names = [n["name"] for n in node_labels.get("nodes", []) if n.get("name")]
    return sorted({n for n in names if n.lower() not in _DROP_LABELS}) or None


def load_pull_requests(
    session: Session,
    repository_id: int,
    nodes: list[dict[str, Any]],
    *,
    resolver: ContributorResolver,
) -> tuple[int, int]:
    """Load one page of PR nodes. Returns `(prs_written, reviews_written)`.

    File rows are written by `load_pr_files` so the nested-connection truncation case can fetch
    more files in a follow-up query before anything hits disk.
    """
    pr_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    pr_ids: dict[int, int] = {}

    for node in nodes:
        author = resolver.resolve(node.get("author"))
        created_at = _parse_dt(node.get("createdAt"))
        if created_at is None:
            continue

        pr_row: dict[str, Any] = {
            "repository_id": repository_id,
            "number": node["number"],
            "title": node.get("title", "")[:1024],
            "state": node.get("state", "OPEN"),
            "author_id": author.id if author else None,
            "created_at": created_at,
            "updated_at": _parse_dt(node.get("updatedAt")),
            "closed_at": _parse_dt(node.get("closedAt")),
            "merged_at": _parse_dt(node.get("mergedAt")),
            "is_draft": bool(node.get("isDraft")),
            "additions": node.get("additions"),
            "deletions": node.get("deletions"),
            "changed_files": node.get("changedFiles"),
            "base_branch": node.get("baseRefName"),
            "head_branch": node.get("headRefName"),
            "labels": _labels(node.get("labels")),
            "truncated_files": False,
            "raw_payload": node,
        }
        pr_rows.append(pr_row)

    # Write PRs one at a time: the reviews in this same page need the (possibly
    # pre-existing) primary key, which bulk upsert does not return.
    written = 0
    for row in pr_rows:
        number = row["number"]
        pr = session.scalars(
            select(PullRequest).where(
                PullRequest.repository_id == repository_id,
                PullRequest.number == number,
            )
        ).one_or_none()
        if pr is None:
            pr = PullRequest(**row)
            session.add(pr)
        else:
            for col in _PR_UPDATE_COLS:
                setattr(pr, col, row[col])
        session.flush()
        pr_ids[number] = pr.id
        written += 1

    for node in nodes:
        pr_id = pr_ids.get(node["number"])
        if pr_id is None:
            continue
        reviews = (node.get("reviews") or {}).get("nodes", [])
        for review in reviews:
            if review.get("state") == "PENDING":
                # A pending review request is not a submitted review (blueprint §6.1).
                continue
            reviewer = resolver.resolve(review.get("author"))
            review_rows.append(
                {
                    "pull_request_id": pr_id,
                    "github_id": review["id"],
                    "reviewer_id": reviewer.id if reviewer else None,
                    "state": review.get("state"),
                    "submitted_at": _parse_dt(review.get("submittedAt")),
                }
            )

    reviews_written = bulk_upsert(
        session,
        PullRequestReview,
        review_rows,
        conflict_target=("pull_request_id", "github_id"),
        update_cols=("reviewer_id", "state", "submitted_at"),
    )

    return written, reviews_written


def load_pr_files(
    session: Session,
    pr_id: int,
    nodes: list[dict[str, Any]],
    *,
    truncated: bool,
) -> int:
    """Load one page of changed files for a PR. Returns files written."""
    if not nodes:
        return 0
    rows = [
        {
            "pull_request_id": pr_id,
            "path": node["path"],
            "additions": node.get("additions"),
            "deletions": node.get("deletions"),
            "is_generated": is_generated_path(node.get("path")),
        }
        for node in nodes
        if node.get("path")
    ]
    return bulk_upsert(
        session,
        FileChange,
        rows,
        conflict_target=("pull_request_id", "path"),
        update_cols=("additions", "deletions", "is_generated"),
    )


def load_issues(
    session: Session,
    repository_id: int,
    nodes: list[dict[str, Any]],
    *,
    resolver: ContributorResolver,
) -> int:
    """Load one page of issue nodes. Returns issues written."""
    rows: list[dict[str, Any]] = []
    for node in nodes:
        created_at = _parse_dt(node.get("createdAt"))
        if created_at is None or node.get("number") is None:
            continue
        author = resolver.resolve(node.get("author"))
        reopened = (node.get("timelineItems") or {}).get("totalCount", 0)
        rows.append(
            {
                "repository_id": repository_id,
                "number": node["number"],
                "title": (node.get("title") or "")[:1024],
                "state": node.get("state", "OPEN"),
                "author_id": author.id if author else None,
                "created_at": created_at,
                "updated_at": _parse_dt(node.get("updatedAt")),
                "closed_at": _parse_dt(node.get("closedAt")),
                "labels": _labels(node.get("labels")),
                "reopened_count": int(reopened or 0),
                "body": node.get("body"),
            }
        )

    return bulk_upsert(
        session,
        Issue,
        rows,
        conflict_target=("repository_id", "number"),
        update_cols=(
            "title",
            "state",
            "author_id",
            "updated_at",
            "closed_at",
            "labels",
            "reopened_count",
            "body",
        ),
    )


def load_commits(
    session: Session,
    repository_id: int,
    nodes: list[dict[str, Any]],
    *,
    resolver: ContributorResolver,
) -> int:
    """Load one page of commit nodes. Returns commits written."""
    rows: list[dict[str, Any]] = []
    for node in nodes:
        committed_at = _parse_dt(node.get("committedDate"))
        sha = node.get("oid")
        if committed_at is None or not sha:
            continue

        # Git author may exist with no linked GitHub user (unclaimed or deleted email).
        # Never attribute such a commit to a real person — record it as a ghost.
        author_node = node.get("author") or {}
        user = author_node.get("user")
        if user is not None:
            author = resolver.resolve(user)
        else:
            author = resolver.resolve_ghost(author_node.get("name"), author_node.get("email"))

        rows.append(
            {
                "repository_id": repository_id,
                "sha": sha,
                "author_id": author.id if author else None,
                "author_name": author_node.get("name"),
                "author_email": author_node.get("email"),
                "committed_at": committed_at,
                "additions": node.get("additions"),
                "deletions": node.get("deletions"),
                "is_merge": bool(node.get("isMerge")),
                "message": node.get("message"),
            }
        )

    return bulk_upsert(
        session,
        Commit,
        rows,
        conflict_target=("repository_id", "sha"),
        update_cols=(
            "author_id",
            "author_name",
            "author_email",
            "committed_at",
            "additions",
            "deletions",
            "is_merge",
            "message",
        ),
    )


def load_releases(
    session: Session,
    repository_id: int,
    items: list[dict[str, Any]],
    *,
    resolver: ContributorResolver,
) -> int:
    """Load one page of REST release objects. Returns releases written.

    Drafts (`published_at` is null) are skipped — a draft is an intent, not a release, and would
    corrupt the deployment-frequency series.
    """
    rows: list[dict[str, Any]] = []
    for item in items:
        published_at = _parse_dt(item.get("published_at"))
        if published_at is None or not item.get("tag_name"):
            continue

        # REST exposes the author as a nested object; resolve it by node id when present.
        author_obj = item.get("author") or {}
        author = resolver.resolve(
            {"id": author_obj.get("node_id"), "login": author_obj.get("login"), "isBot": None}
            if author_obj.get("node_id")
            else None
        )

        rows.append(
            {
                "repository_id": repository_id,
                "tag": item["tag_name"],
                "name": (item.get("name") or "")[:255] or None,
                "author_id": author.id if author else None,
                "published_at": published_at,
            }
        )

    return bulk_upsert(
        session,
        Release,
        rows,
        conflict_target=("repository_id", "tag"),
        update_cols=("name", "author_id", "published_at"),
    )
