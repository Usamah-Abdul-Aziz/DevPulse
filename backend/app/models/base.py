"""SQLAlchemy declarative base.

All models inherit from `Base`. Alembic autogenerate detects changes from here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator


class JSONB(TypeDecorator[dict[str, Any] | list[Any] | None]):
    """JSON column that is `JSONB` on Postgres and plain `JSON` elsewhere.

    The data model calls for JSONB (`docs/architecture.md` §4: raw payloads, labels, SHAP). Unit
    tests run on in-memory SQLite, where JSONB does not exist, so this decorator keeps the model
    declarations dialect-agnostic while production still gets real JSONB columns.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(sqlite.JSON())


class Base(DeclarativeBase):
    """Project-wide declarative base with shared timestamp columns."""


class TimestampMixin:
    """`created_at` / `updated_at` on every row."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
