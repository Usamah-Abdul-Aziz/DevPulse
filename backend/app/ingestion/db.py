"""Dialect-aware bulk upsert.

Idempotency is the Phase 2 acceptance criterion, and it rests here: every ingestion write goes
through `bulk_upsert`, which resolves to `INSERT ... ON CONFLICT ... DO UPDATE` on Postgres and to
`OR REPLACE` on SQLite. Re-ingesting the same page must update rows in place, never duplicate them.

SQLite's `INSERT OR REPLACE` deletes and re-inserts the conflicting row, which would churn row ids
and break FKs pointing at them — so on SQLite we fall back to a load-then-merge that preserves ids.
That path is only used by tests; production runs on Postgres.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

T = TypeVar("T")


def bulk_upsert(
    session: Session,
    model: type[T],
    rows: Sequence[dict[str, Any]],
    *,
    conflict_target: Sequence[str],
    update_cols: Sequence[str],
) -> int:
    """Upsert `rows` into `model`, keyed on `conflict_target`. Returns the number of rows written.

    `update_cols` are the columns refreshed when an existing row is found. Columns omitted from
    `update_cols` keep their existing value — used deliberately for immutable fields.
    """
    if not rows:
        return 0

    dialect_name = session.bind.dialect.name if session.bind else "unknown"

    if dialect_name == "postgresql":
        stmt = postgresql.insert(model).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=list(conflict_target),
            set_={col: getattr(stmt.excluded, col) for col in update_cols},
        )
        session.execute(stmt)
        return len(rows)

    # SQLite: preserve row ids by loading existing rows and merging in Python.
    # Tests run here; a naive `OR REPLACE` would delete and re-create rows, which
    # invalidates foreign keys and makes id assertions meaningless.
    return _sqlite_merge(
        session, model, rows, conflict_target=conflict_target, update_cols=update_cols
    )


def _sqlite_merge(
    session: Session,
    model: type[T],
    rows: Sequence[dict[str, Any]],
    *,
    conflict_target: Sequence[str],
    update_cols: Sequence[str],
) -> int:
    mapper = inspect(model)
    pk_cols = [c.key for c in mapper.primary_key]

    existing = {
        tuple(getattr(obj, col) for col in conflict_target): obj
        for obj in session.scalars(
            select(model).where(
                *[getattr(model, col).in_({row[col] for row in rows}) for col in conflict_target]
            )
        ).all()
    }

    written = 0
    for row in rows:
        key = tuple(row[col] for col in conflict_target)
        obj = existing.get(key)
        if obj is None:
            session.add(
                model(**{k: v for k, v in row.items() if k not in pk_cols or v is not None})
            )
            written += 1
        else:
            for col in update_cols:
                if col in row:
                    setattr(obj, col, row[col])
            written += 1

    session.flush()
    return written
