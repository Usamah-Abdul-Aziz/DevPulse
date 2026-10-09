"""GitHub client tests against an `httpx.MockTransport`.

The transport is injected for exactly this reason (AGENTS.md): these tests exercise the wire-level
contract — pagination cursors, rate-limit headers, error codes — without touching the network.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.ingestion.errors import (
    GitHubError,
    GraphQLResponseError,
    RateLimitedTransient,
    RateLimitExhausted,
    RepositoryNotFound,
)
from app.ingestion.github_client import GitHubClient
from app.ingestion.queries import PULL_REQUESTS_QUERY, REPOSITORY_QUERY


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "github_token": "test-token",
        "ingestion_min_rate_budget": 200,
        "ingestion_request_timeout": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class CountingTransport(httpx.MockTransport):
    """Mock transport that records requests and can serve staged responses per call."""

    def __init__(self, handler: Any) -> None:
        self.requests: list[httpx.Request] = []
        self.call_count = 0
        super().__init__(self._wrap(handler))

    def _wrap(self, handler: Any) -> Any:
        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            self.call_count += 1
            return handler(request, self.call_count)

        return wrapped


def graphql_body(
    data: dict[str, Any], *, remaining: int = 5000, errors: list | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "data": data,
        "rateLimit": {
            "remaining": remaining,
            "cost": 1,
            "limit": 5000,
            "resetAt": "2026-10-10T00:00:00Z",
        },
    }
    if errors is not None:
        body["errors"] = errors
    return body


def make_client(
    handler: Any, **settings_overrides: object
) -> tuple[GitHubClient, CountingTransport]:
    transport = CountingTransport(handler)
    return GitHubClient(
        settings=make_settings(**settings_overrides), transport=transport
    ), transport


class TestGraphql:
    def test_returns_the_data_object(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(200, json=graphql_body({"repository": {"name": "widgets"}}))

        client, _ = make_client(handler)
        try:
            data = client.get_repository("acme", "widgets")
        finally:
            client.close()
        assert data == {"repository": {"name": "widgets"}}

    def test_sends_the_bearer_token(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer test-token"
            return httpx.Response(200, json=graphql_body({"repository": {}}))

        client, _ = make_client(handler)
        try:
            client.get_repository("acme", "widgets")
        finally:
            client.close()

    def test_pagination_passes_the_end_cursor(self) -> None:
        cursors: list[str | None] = []

        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            variables = json.loads(request.content)["variables"]
            cursors.append(variables.get("after"))
            if _count == 1:
                return httpx.Response(
                    200,
                    json=graphql_body(
                        {
                            "repository": {
                                "pullRequests": {
                                    "pageInfo": {"hasNextPage": True, "endCursor": "abc"},
                                    "nodes": [{"number": 1}],
                                }
                            }
                        }
                    ),
                )
            return httpx.Response(
                200,
                json=graphql_body(
                    {
                        "repository": {
                            "pullRequests": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [{"number": 2}],
                            }
                        }
                    }
                ),
            )

        client, transport = make_client(handler)
        try:
            first = client.fetch_pull_requests("acme", "widgets", first=10)
            second = client.fetch_pull_requests(
                "acme",
                "widgets",
                first=10,
                after=first["repository"]["pullRequests"]["pageInfo"]["endCursor"],
            )
        finally:
            client.close()

        assert cursors == [None, "abc"]
        assert transport.call_count == 2
        assert second["repository"]["pullRequests"]["nodes"] == [{"number": 2}]

    def test_errors_in_the_body_raise(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(
                200, json=graphql_body({}, errors=[{"message": "field 'nope' does not exist"}])
            )

        client, _ = make_client(handler)
        with pytest.raises(GraphQLResponseError, match="field 'nope'"):
            client.graphql(REPOSITORY_QUERY, {"owner": "acme", "name": "widgets"})
        client.close()

    def test_missing_data_and_missing_errors_raise(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(200, json={"rateLimit": {"remaining": 5000}})

        client, _ = make_client(handler)
        with pytest.raises(GraphQLResponseError):
            client.graphql(REPOSITORY_QUERY, {"owner": "acme", "name": "widgets"})
        client.close()


class TestRateBudget:
    def test_raises_before_the_budget_runs_out(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(200, json=graphql_body({"repository": {}}, remaining=150))

        client, _ = make_client(handler)
        try:
            with pytest.raises(RateLimitExhausted) as exc_info:
                client.graphql(
                    PULL_REQUESTS_QUERY, {"owner": "acme", "name": "widgets", "first": 10}
                )
        finally:
            client.close()

        # 150 < the 200 threshold, and the message must carry the reset time.
        assert exc_info.value.remaining == 150
        assert exc_info.value.reset_at == "2026-10-10T00:00:00Z"

    def test_rest_reads_the_headers(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(
                200,
                json=[{"tag_name": "v1"}],
                headers={"x-ratelimit-remaining": "42", "x-ratelimit-reset": "1893456000"},
            )

        client, _ = make_client(handler)
        try:
            assert client.rest("/repos/acme/widgets/releases") == [{"tag_name": "v1"}]
            assert client.remaining == 42
        finally:
            client.close()

    def test_rest_pause_uses_the_budget(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(200, json=[], headers={"x-ratelimit-remaining": "5"})

        client, _ = make_client(handler)
        try:
            # The first call drains the budget to 5; the second must refuse to spend it.
            client.rest("/repos/acme/widgets/releases")
            with pytest.raises(RateLimitExhausted):
                client.rest("/repos/acme/widgets/releases")
        finally:
            client.close()


class TestStatusCodes:
    def test_404_raises_repository_not_found(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        client, _ = make_client(handler)
        with pytest.raises(RepositoryNotFound):
            client.get_repository("acme", "missing")
        client.close()

    def test_500_is_retried_then_raised_as_transient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The backoff is exponential with jitter; neutralise the sleeps so the retry
        # *count* is what the test asserts on, not how long it took.
        monkeypatch.setattr("app.ingestion.github_client.random.uniform", lambda _lo, _hi: 0.0)

        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client, transport = make_client(handler)
        with pytest.raises(RateLimitedTransient):
            client.get_repository("acme", "widgets")
        # Retries are a property of the retry policy, so all attempts were used.
        assert transport.call_count == 5
        client.close()

    def test_429_is_retried_and_can_succeed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.ingestion.github_client.random.uniform", lambda _lo, _hi: 0.0)

        def handler(request: httpx.Request, count: int) -> httpx.Response:
            if count < 2:
                return httpx.Response(429, text="slow down", headers={"retry-after": "0"})
            return httpx.Response(200, json=graphql_body({"repository": {"name": "widgets"}}))

        client, transport = make_client(handler)
        try:
            data = client.get_repository("acme", "widgets")
        finally:
            client.close()
        assert data["repository"]["name"] == "widgets"
        assert transport.call_count == 2

    def test_400_raises_a_plain_github_error(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(400, text="bad request")

        client, _ = make_client(handler)
        with pytest.raises(GitHubError) as exc_info:
            client.rest("/repos/acme/widgets")
        client.close()
        assert not isinstance(exc_info.value, RateLimitedTransient)


class TestContextManager:
    def test_context_manager_closes_the_client(self) -> None:
        def handler(request: httpx.Request, _count: int) -> httpx.Response:
            return httpx.Response(200, json=graphql_body({"repository": {}}))

        with make_client(handler)[0] as client:
            assert isinstance(client, GitHubClient)
