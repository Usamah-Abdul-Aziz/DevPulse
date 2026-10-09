"""Test helpers: a fake GitHub that speaks the same page/cursor protocol as the real API.

Every Phase 2 behaviour worth testing — incremental windows, resume, truncation — is a consequence
of how the client and pipeline agree on pagination, so the fake has to honour that agreement
faithfully rather than returning canned dicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.ingestion.errors import RateLimitExhausted


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def pr_node(
    number: int,
    *,
    updated: datetime,
    created: datetime | None = None,
    author: str = "octocat",
    author_id: str = "U_1",
    state: str = "MERGED",
    title: str | None = None,
    files: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    total_files: int | None = None,
) -> dict[str, Any]:
    """One `PULL_REQUESTS_QUERY` node, with sensible defaults for the fields we do not assert on."""
    if files is None:
        files = [{"path": "src/main.py", "additions": 10, "deletions": 2}]
    if reviews is None:
        reviews = [
            {
                "id": f"R_{number}",
                "author": {"id": "U_2", "login": "reviewer", "isBot": False},
                "state": "APPROVED",
                "submittedAt": iso(updated),
            }
        ]
    total = total_files if total_files is not None else len(files)
    return {
        "id": f"PR_{number}",
        "number": number,
        "title": title if title is not None else f"PR #{number}",
        "state": state,
        "isDraft": False,
        "createdAt": iso(created if created is not None else updated - timedelta(days=1)),
        "updatedAt": iso(updated),
        "closedAt": iso(updated) if state != "OPEN" else None,
        "mergedAt": iso(updated) if state == "MERGED" else None,
        "author": {"id": author_id, "login": author, "isBot": author.endswith("[bot]")},
        "additions": 30,
        "deletions": 5,
        "changedFiles": total,
        "baseRefName": "main",
        "headRefName": f"feature-{number}",
        "labels": {"nodes": [{"name": "bug"}]},
        "body": f"Body of PR #{number}",
        "reviews": {"nodes": reviews},
        "files": {
            "totalCount": total,
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": files,
        },
    }


def issue_node(
    number: int,
    *,
    updated: datetime,
    created: datetime | None = None,
    author: str = "octocat",
    author_id: str = "U_1",
    state: str = "CLOSED",
) -> dict[str, Any]:
    return {
        "id": f"I_{number}",
        "number": number,
        "title": f"Issue #{number}",
        "state": state,
        "createdAt": iso(created if created is not None else updated - timedelta(days=2)),
        "updatedAt": iso(updated),
        "closedAt": iso(updated) if state != "OPEN" else None,
        "author": {"id": author_id, "login": author, "isBot": False},
        "labels": {"nodes": []},
        "body": f"Body of issue #{number}",
        "timelineItems": {"totalCount": 1 if number % 3 == 0 else 0},
    }


def commit_node(
    sha: str,
    *,
    committed: datetime,
    author_login: str | None = "octocat",
    name: str = "Octocat",
    email: str = "octocat@github.com",
) -> dict[str, Any]:
    user = {"id": "U_1", "login": author_login, "isBot": False} if author_login else None
    return {
        "id": f"C_{sha}",
        "oid": sha,
        "committedDate": iso(committed),
        "additions": 4,
        "deletions": 1,
        "isMerge": False,
        "message": f"Commit {sha}",
        "author": {"name": name, "email": email, "user": user},
    }


def _page_info(index: int, pages: list[list[dict[str, Any]]]) -> dict[str, Any]:
    has_next = index + 1 < len(pages)
    return {"hasNextPage": has_next, "endCursor": f"cursor-{index + 1}" if has_next else None}


class FakeGitHubClient:
    """Records calls and serves pre-built pages, tracking cursors the way GitHub does."""

    def __init__(
        self,
        *,
        pr_pages: list[list[dict[str, Any]]] | None = None,
        issue_pages: list[list[dict[str, Any]]] | None = None,
        commit_pages: list[list[dict[str, Any]]] | None = None,
        releases: list[dict[str, Any]] | None = None,
        repo: dict[str, Any] | None = None,
        remaining: int = 5000,
    ) -> None:
        self.pr_pages = pr_pages or []
        self.issue_pages = issue_pages or []
        self.commit_pages = commit_pages or []
        self.releases = releases or []
        self.repo = (
            repo
            if repo is not None
            else {
                "repository": {
                    "defaultBranchRef": {"name": "main"},
                    "pullRequests": {"totalCount": 3},
                }
            }
        )
        self.remaining = remaining
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._pr_index = 0
        self._issue_index = 0
        self._commit_index = 0
        self._rate_limit_after_calls: int | None = None

    # -- test knobs ----------------------------------------------------------

    def exhaust_rate_limit_after(self, calls: int) -> None:
        """Raise `RateLimitExhausted` once this many calls have been served (simulates a pause)."""
        self._rate_limit_after_calls = calls

    # -- protocol (mirrors GitHubClient) ------------------------------------

    def get_repository(self, owner: str, name: str) -> dict[str, Any]:
        self.calls.append(("get_repository", {"owner": owner, "name": name}))
        return self.repo

    def fetch_pull_requests(
        self, owner: str, name: str, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        self._maybe_exhaust()
        self.calls.append(("fetch_pull_requests", {"first": first, "after": after}))
        nodes = self.pr_pages[self._pr_index] if self._pr_index < len(self.pr_pages) else []
        page = _page_info(self._pr_index, self.pr_pages)
        if self._pr_index < len(self.pr_pages):
            self._pr_index += 1
        return {
            "repository": {
                "pullRequests": {
                    "totalCount": sum(len(p) for p in self.pr_pages),
                    "pageInfo": page,
                    "nodes": nodes,
                }
            }
        }

    def fetch_pr_files(
        self, owner: str, name: str, number: int, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        self._maybe_exhaust()
        self.calls.append(("fetch_pr_files", {"number": number, "first": first, "after": after}))
        # Return one follow-up page of a single file, then stop.
        nodes = [] if after else [{"path": f"gen-{number}.lock", "additions": 1, "deletions": 0}]
        return {
            "repository": {
                "pullRequest": {
                    "files": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": nodes,
                    }
                }
            }
        }

    def fetch_issues(
        self, owner: str, name: str, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        self._maybe_exhaust()
        self.calls.append(("fetch_issues", {"first": first, "after": after}))
        nodes = (
            self.issue_pages[self._issue_index] if self._issue_index < len(self.issue_pages) else []
        )
        page = _page_info(self._issue_index, self.issue_pages)
        if self._issue_index < len(self.issue_pages):
            self._issue_index += 1
        return {
            "repository": {
                "issues": {
                    "totalCount": sum(len(p) for p in self.issue_pages),
                    "pageInfo": page,
                    "nodes": nodes,
                }
            }
        }

    def fetch_commits(
        self,
        owner: str,
        name: str,
        branch: str,
        *,
        first: int,
        after: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        self._maybe_exhaust()
        self.calls.append(
            (
                "fetch_commits",
                {"branch": branch, "first": first, "after": after, "since": since, "until": until},
            )
        )
        nodes = (
            self.commit_pages[self._commit_index]
            if self._commit_index < len(self.commit_pages)
            else []
        )
        page = _page_info(self._commit_index, self.commit_pages)
        if self._commit_index < len(self.commit_pages):
            self._commit_index += 1
        return {
            "repository": {
                "ref": {
                    "name": branch,
                    "target": {
                        "history": {
                            "totalCount": sum(len(p) for p in self.commit_pages),
                            "pageInfo": page,
                            "nodes": nodes,
                        }
                    },
                }
            }
        }

    def rest(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self._maybe_exhaust()
        self.calls.append(("rest", {"path": path, "params": params}))
        per_page = (params or {}).get("per_page", 100)
        page = (params or {}).get("page", 1)
        start = (page - 1) * per_page
        if start >= len(self.releases):
            return []
        return self.releases[start : start + per_page]

    def close(self) -> None:
        pass

    def __enter__(self) -> FakeGitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    # -- internals ------------------------------------------------------------

    def _maybe_exhaust(self) -> None:
        if (
            self._rate_limit_after_calls is not None
            and len(self.calls) >= self._rate_limit_after_calls
        ):
            self._rate_limit_after_calls = None
            raise RateLimitExhausted(reset_at="1893456000", remaining=10, resource="graphql")
