"""Ingestion job schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.types import TimestampOptional

#: Mirrors the CHECK constraint on `ingestion_jobs.status`.
JOB_STATUS_VALUES = ("pending", "running", "paused", "succeeded", "failed")


class JobResponse(BaseModel):
    """An ingestion job, as returned by `GET /api/v1/jobs/{job_id}`.

    `resume_after` is set only for `paused` jobs — it is GitHub's rate-limit reset time and the
    earliest moment the job should be resumed. `counts` are running totals per entity.
    """

    id: int
    repository_id: int
    status: str = Field(examples=["succeeded"])
    started_at: TimestampOptional = None
    finished_at: TimestampOptional = None
    resume_after: TimestampOptional = None
    cursor: dict | None = Field(
        default=None,
        description="Resume state: the phase and per-phase page cursors.",
        examples=[{"phase": "done", "cursors": {}, "mode": "full", "history_months": 24}],
    )
    counts: dict | None = Field(
        default=None,
        examples=[{"prs": 42, "issues": 17, "commits": 331, "releases": 5, "api_calls": 12}],
    )
    error: str | None = None

    model_config = {"from_attributes": True}
