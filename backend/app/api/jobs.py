"""Job endpoints: read ingestion job state.

Polling this is how the frontend follows a connect (Phase 2). There is no endpoint to *start* a
job directly — jobs start from `POST /repositories/connect` only, so the allow-list gate cannot be
bypassed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.errors import HTTPProblem
from app.core.database import get_db
from app.models import IngestionJob
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    """One ingestion job: status, counts, cursor, and `resume_after` when paused."""
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPProblem(status.HTTP_404_NOT_FOUND, f"Ingestion job {job_id} not found.")
    return JobResponse.model_validate(job)
