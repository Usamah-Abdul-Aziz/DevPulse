"""Exceptions for the ingestion layer.

The distinction that matters is *resumable* vs. *terminal*: a rate-limit exhaustion pauses the job
so it can resume from the cursor, everything else fails it.
"""

from __future__ import annotations


class GitHubError(Exception):
    """Base class for all ingestion failures."""


class RepositoryNotFound(GitHubError):
    """The repository does not exist or is not visible to the token (404)."""


class RateLimitExhausted(GitHubError):
    """The remaining rate-limit budget fell below the pause threshold.

    Carries `reset_at` so the job can record when it may resume. Raised *before* the budget hits
    zero, so the current page is never half-written.
    """

    def __init__(self, reset_at: str | None, remaining: int, *, resource: str = "graphql") -> None:
        self.reset_at = reset_at
        self.remaining = remaining
        self.resource = resource
        super().__init__(
            f"{resource} rate budget exhausted: {remaining} points remaining, resets at {reset_at}"
        )


class RateLimitedTransient(GitHubError):
    """A secondary rate limit or 5xx — retryable after backoff (blueprint §13.2)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message)


class GraphQLResponseError(GitHubError):
    """The GraphQL endpoint returned `errors` in the response body."""


class IngestionError(Exception):
    """A pipeline-level failure that should fail the job with a user-facing message."""
