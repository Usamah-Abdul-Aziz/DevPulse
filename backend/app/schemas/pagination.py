"""Pagination envelope shared by every list endpoint (docs/api.md).

    { "items": [...], "page": 1, "limit": 20, "total": 137 }

Page numbers are 1-based; `limit` echoes what was actually applied (after clamping to `max_limit`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def clamp_limit(limit: int | None) -> int:
    """Apply the documented default and ceiling to a `limit` query parameter."""
    if limit is None or limit < 1:
        return DEFAULT_LIMIT
    return min(limit, MAX_LIMIT)


class Page(BaseModel, Generic[T]):
    """One page of a paginated collection."""

    items: Sequence[T]
    page: int = Field(ge=1, examples=[1])
    limit: int = Field(ge=1, examples=[DEFAULT_LIMIT])
    total: int = Field(ge=0, examples=[137])
