"""Commit model.

Commits are the default-branch history only (`ref(qualifiedName: defaultBranch).target.history`),
not every commit on every branch — that is the set the API exposes cheaply and the only set the
metrics consume.

`author_name` / `author_email` are kept *in addition to* `author_id` because a commit's git author
may have no linked GitHub account (unclaimed email, deleted user). Without the raw strings those
commits would become unattributable; with them, identity merging stays possible later (ADR-010).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Commit(Base):
    """Commit.

    No `TimestampMixin`: `committed_at` is the GitHub commit timestamp analytics uses, and there is
    no other natural "row created" time worth storing for a fact table.
    """

    __tablename__ = "commits"
    __table_args__ = (
        UniqueConstraint("repository_id", "sha", name="uq_commits_repo_sha"),
        Index("ix_commits_repo_committed_at", "repository_id", "committed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    #: Full 40-char SHA; short SHAs are not unique across a long history.
    sha: Mapped[str] = mapped_column(String(40), nullable=False)

    author_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: `committedDate`, which is when the commit landed on the branch — the timestamp metrics use.
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Merge commits (`parents.totalCount > 1`) are excluded from commit-frequency metrics
    #: (blueprint §6.1) — in squash-merge repos they would otherwise double-count every PR.
    is_merge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    #: Kept for the revert-detection half of the label heuristic (`docs/ml.md` §2a).
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    repository = relationship("Repository", back_populates="commits")
    author = relationship("Contributor", foreign_keys=[author_id])
