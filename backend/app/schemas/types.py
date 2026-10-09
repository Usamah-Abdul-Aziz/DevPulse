"""Shared schema types.

`Timestamp` guarantees every timestamp on the wire carries a timezone offset (docs/api.md). Postgres
preserves `DateTime(timezone=True)`, but a value read back from SQLite arrives naive — without this
serializer the API would emit `2026-10-09T01:40:16` in one environment and
`2026-10-09T01:40:16+00:00` in another, and the frontend could not parse either uniformly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from app.core.dates import as_utc


def _serialize_timestamp(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return as_utc(dt).isoformat()


Timestamp = Annotated[
    datetime,
    PlainSerializer(_serialize_timestamp, return_type=str | None, when_used="json"),
]

TimestampOptional = Annotated[
    datetime | None,
    PlainSerializer(_serialize_timestamp, return_type=str | None, when_used="json"),
]
