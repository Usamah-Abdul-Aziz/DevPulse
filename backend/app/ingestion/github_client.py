"""GitHub API client: GraphQL for most entities, REST for releases.

Rate limits (blueprint §13.2): every request reads the remaining budget and the client raises
`RateLimitExhausted` *before* it would drop below `ingestion_min_rate_budget`, so a job pauses
cleanly rather than burning a request against a zero budget. Transient secondary limits and 5xx
are retried with exponential backoff and jitter (`tenacity`), respecting `retry-after` when GitHub
provides it.

The client is transport-injected: `httpx.MockTransport` in tests, a real `httpx.Client` in
production. That is what lets the pipeline be tested against a mocked GitHub (AGENTS.md).
"""

from __future__ import annotations

import logging
import random
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.core.config import Settings, get_settings
from app.ingestion.errors import (
    GitHubError,
    GraphQLResponseError,
    RateLimitedTransient,
    RateLimitExhausted,
    RepositoryNotFound,
)
from app.ingestion.queries import (
    COMMITS_QUERY,
    ISSUES_QUERY,
    PR_FILES_QUERY,
    PULL_REQUESTS_QUERY,
    REPOSITORY_QUERY,
)

log = logging.getLogger(__name__)

#: Retry the flaky stuff, not hard failures.
_MAX_RETRIES = 5


def _wait_with_retry_after(retry_state: Any) -> float:
    """Exponential backoff with full jitter, overridden by GitHub's `retry-after` when present.

    Full jitter (`uniform(0, exponential)`) is the variance-reducing kind: it avoids the
    thundering-herd retry bursts that fixed backoff produces.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        return float(retry_after)
    attempt = retry_state.attempt_number
    return random.uniform(0, min(30, 2**attempt))


class GitHubClient:
    """Thin GraphQL/REST wrapper that tracks the rate-limit budget."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._remaining: int | None = None
        self._reset_at: str | None = None
        self._token = self.settings.github_token

        client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(self.settings.ingestion_request_timeout),
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.Client(**client_kwargs)

        # `Authorization` is only sent when a token exists: unauthenticated REST still
        # works at 60 req/h, and tests that only exercise pagination skip the header.
        self._headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- budget ---------------------------------------------------------------

    @property
    def remaining(self) -> int | None:
        """Rate-limit points left on the most recently used resource."""
        return self._remaining

    def _check_budget(self, resource: str) -> None:
        """Pause before the budget would run out (blueprint §13.2)."""
        remaining = self._remaining
        if remaining is not None and remaining < self.settings.ingestion_min_rate_budget:
            raise RateLimitExhausted(
                reset_at=self._reset_at, remaining=remaining, resource=resource
            )

    def _update_budget_from_headers(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining is not None and remaining.isdigit():
            self._remaining = int(remaining)
        if reset is not None and reset.isdigit():
            self._reset_at = str(int(reset))

    def _raise_for_status(self, response: httpx.Response, *, graphql: bool) -> None:
        status = response.status_code

        if status in (403, 429):
            # Secondary rate limits come as 403 with a `retry-after` header.
            retry_after = response.headers.get("retry-after")
            message = response.text[:200]
            raise RateLimitedTransient(
                f"GitHub returned {status}: {message}",
                retry_after=float(retry_after) if retry_after else None,
            )

        if status == 404:
            raise RepositoryNotFound(f"GitHub returned 404 for {response.url}")

        if status >= 500:
            raise RateLimitedTransient(f"GitHub returned {status}: {response.text[:200]}")

        if status >= 400:
            raise GitHubError(f"GitHub returned {status}: {response.text[:200]}")

        if graphql:
            # GraphQL always answers 200; real errors live in the body.
            body = response.json()
            if body.get("errors"):
                messages = "; ".join(str(e.get("message", ""))[:200] for e in body["errors"])
                raise GraphQLResponseError(messages)

    # -- transport ------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """One request, with backoff on transient failures."""
        headers = {**self._headers, **kwargs.pop("headers", {})}
        return self._request_with_retry(method, url, headers=headers, **kwargs)

    @retry(
        retry=retry_if_exception_type(RateLimitedTransient),
        stop=stop_after_attempt(_MAX_RETRIES),
        wait=_wait_with_retry_after,
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise RateLimitedTransient(f"transport error: {exc}") from exc

        self._update_budget_from_headers(response)
        self._raise_for_status(response, graphql=kwargs.get("json", {}).get("query") is not None)
        return response

    # -- GraphQL --------------------------------------------------------------

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one GraphQL query and return the `data` object.

        Raises `RateLimitExhausted` when the remaining budget is below the pause threshold,
        evaluated *before* the request so a job never starts a page it cannot finish.
        """
        self._check_budget("graphql")
        payload = {"query": query, "variables": variables or {}}
        response = self._request(
            "POST",
            self.settings.github_graphql_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        body = response.json()

        rate_limit = body.get("rateLimit")
        if rate_limit:
            self._remaining = int(rate_limit.get("remaining", 0))
            self._reset_at = rate_limit.get("resetAt")

        self._check_budget("graphql")

        if body.get("errors"):
            messages = "; ".join(str(e.get("message", ""))[:200] for e in body["errors"])
            raise GraphQLResponseError(messages)

        data = body.get("data")
        if data is None:
            raise GraphQLResponseError("GraphQL response had no data and no errors")
        return data

    # -- REST -----------------------------------------------------------------

    def rest(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """One REST GET, returning the parsed JSON body."""
        self._check_budget("rest")
        url = f"{self.settings.github_api_url.rstrip('/')}/{path.lstrip('/')}"
        response = self._request("GET", url, params=params)
        return response.json()

    # -- convenience wrappers --------------------------------------------------

    def get_repository(self, owner: str, name: str) -> dict[str, Any]:
        return self.graphql(REPOSITORY_QUERY, {"owner": owner, "name": name})

    def fetch_pull_requests(
        self, owner: str, name: str, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        return self.graphql(
            PULL_REQUESTS_QUERY, {"owner": owner, "name": name, "first": first, "after": after}
        )

    def fetch_pr_files(
        self, owner: str, name: str, number: int, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        return self.graphql(
            PR_FILES_QUERY,
            {"owner": owner, "name": name, "number": number, "first": first, "after": after},
        )

    def fetch_issues(
        self, owner: str, name: str, *, first: int, after: str | None = None
    ) -> dict[str, Any]:
        return self.graphql(
            ISSUES_QUERY, {"owner": owner, "name": name, "first": first, "after": after}
        )

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
        return self.graphql(
            COMMITS_QUERY,
            {
                "owner": owner,
                "name": name,
                "branch": branch,
                "first": first,
                "after": after,
                "since": since,
                "until": until,
            },
        )
