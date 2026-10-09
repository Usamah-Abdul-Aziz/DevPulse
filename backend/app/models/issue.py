"""Issue model.

Issues are separate from pull requests in GraphQL (unlike the REST API, which conflates them), so
this table holds issues only. Labels are stored as a name list because the label heuristic in
`docs/ml.md` §2 needs to know whether a *bug-type* label is present, and a JSON list is the
simplest representation that stays readable in a query result.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import JSONB, Base


class Issue(Base):
    """Issue.

    Like `PullRequest`, this model does not use `TimestampMixin`: `created_at` / `updated_at` are
    GitHub-sourced values that analytics depends on, not row-local ingestion stamps.
    """

    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_issues_repo_number"),
        Index("ix_issues_repo_created_at", "repository_id", "created_at"),
        Index("ix_issues_repo_updated_at", "repository_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)

    author_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    labels: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    reopened_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    repository = relationship("Repository", back_populates="issues")
    author = relationship("Contributor", foreign_keys=[author_id])
