"""Pull request model, its reviews, and the files it touched.

The PR table carries the raw GitHub node in `raw_payload` (blueprint §12) so re-extraction of
derived fields later never requires re-fetching the API.

Timing columns drive the cycle-time decomposition (blueprint §6.2):

    cycle   = merged_at  - created_at
    pickup  = first_review_at - created_at   (computed in Phase 3 from pull_request_reviews)
    review  = approved_at - first_review_at
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import JSONB, Base, TimestampMixin


class PullRequest(Base):
    """Pull request.

    Note on timestamps: this model deliberately does *not* use `TimestampMixin`. Its `created_at`
    / `updated_at` come from GitHub and are the values analytics consumes; a row-local ingestion
    timestamp would collide with them. When a row was fetched is recoverable from
    `repositories.last_synced_at`.
    """

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pull_requests_repo_number"),
        Index("ix_pull_requests_repo_created_at", "repository_id", "created_at"),
        Index("ix_pull_requests_repo_updated_at", "repository_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    #: GitHub PR number, unique within the repository.
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)

    #: OPEN / CLOSED / MERGED as returned by GraphQL (`PullRequestState`).
    state: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Author, NULL for ghost (deleted) users — the raw login survives in `raw_payload`.
    author_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_files: Mapped[int | None] = mapped_column(Integer, nullable=True)

    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: Issue labels as a simple name list — queried for display, never for joins.
    labels: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    #: True when the file list was truncated at `INGESTION_MAX_FILE_CHANGES_PER_PR` (ADR-006).
    truncated_files: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    #: The raw GraphQL node. Kept small: file/review edges live in their own tables.
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    repository = relationship("Repository", back_populates="pull_requests")
    author = relationship("Contributor", foreign_keys=[author_id])
    reviews = relationship(
        "PullRequestReview", back_populates="pull_request", cascade="all, delete-orphan"
    )
    file_changes = relationship(
        "FileChange", back_populates="pull_request", cascade="all, delete-orphan"
    )


class PullRequestReview(Base, TimestampMixin):
    __tablename__ = "pull_request_reviews"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "github_id", name="uq_reviews_pr_github_id"),
        Index("ix_reviews_pr_submitted_at", "pull_request_id", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False
    )

    #: GraphQL node id — stable across re-ingestion, so reviews upsert cleanly.
    github_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), nullable=True)

    #: APPROVED / CHANGES_REQUESTED / COMMENTED / DISMISSED. PENDING rows are request edges,
    #: not submitted reviews, and are never written (blueprint §6.1: draft/request time excluded).
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pull_request = relationship("PullRequest", back_populates="reviews")
    reviewer = relationship("Contributor", foreign_keys=[reviewer_id])


class FileChange(Base, TimestampMixin):
    """One file touched by one pull request.

    `is_generated` is set by the path rules in `app.ingestion.cleaning` so generated/vendored
    content stays out of churn and PR-size metrics (blueprint §6.1) while remaining in the DB —
    the filter stays auditable, never a silent delete.
    """

    __tablename__ = "file_changes"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "path", name="uq_file_changes_pr_path"),
        Index("ix_file_changes_pr_path", "pull_request_id", "path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=True
    )
    #: Reserved for commit-scoped changes (hotspots, Phase 9); unused in Phase 2.
    commit_id: Mapped[int | None] = mapped_column(ForeignKey("commits.id"), nullable=True)

    path: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    pull_request = relationship("PullRequest", back_populates="file_changes")
