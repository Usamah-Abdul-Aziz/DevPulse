"""Datetime helpers.

Postgres preserves `DateTime(timezone=True)` on round-trip; SQLite does not, so a value read back
from the test database arrives naive and cannot be compared against a timezone-aware timestamp.
Everything that compares a stored timestamp to an in-memory one normalizes through here.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(dt: datetime) -> datetime:
    """Assume a naive timestamp is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
