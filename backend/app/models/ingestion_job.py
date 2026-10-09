"""Ingestion job model — the unit of asynchronous, resumable ingestion.

Lifecycle:

    pending → running → succeeded
                     ↘ paused  (rate budget exhausted; `resume_after` is the reset time)
                     ↘ failed  (unrecoverable error, message in `error`)

`cursor` is persisted after *every* fetched page, so a job that stops mid-phase resumes from the
next page rather than redoing the phase. Combined with natural-key upserts everywhere else, that
makes re-running a job idempotent (ADR-009).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import JSONB, Base, TimestampMixin

#: Non-terminal states a `POST /connect` should not start a new job against.
JOB_ACTIVE_STATES = ("pending", "running")
JOB_TERMINAL_STATES = ("succeeded", "failed")
#: Every status the column may hold; enforced by a CHECK in the migration.
JOB_STATUSES = ("pending", "running", "paused", "succeeded", "failed")


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="ck_ingestion_jobs_status"),
        Index("ix_ingestion_jobs_repo_started_at", "repository_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Earliest moment a paused job may resume (GitHub rate-limit reset). NULL otherwise.
    resume_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: JSON: {phase, cursors: {...}, window_start, window_end, history_months, mode}.
    cursor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: Truncated to 500 chars by the runner — error detail is user-facing, never a stack dump.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Running totals, JSON: {prs, reviews, issues, commits, files, releases, api_calls, ...}.
    counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    repository = relationship("Repository", back_populates="ingestion_jobs")
