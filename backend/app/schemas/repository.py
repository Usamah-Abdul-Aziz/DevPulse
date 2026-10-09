"""Repository schemas.

`full_name` is the user-facing key (`owner/name`); the numeric `id` is the API handle.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.types import TimestampOptional

_MAX_FULL_NAME = 255


def _normalize_repository(value: str) -> str:
    """Accept `owner/name`, a full GitHub URL, or `host/owner/name`, and return `owner/name`.

    Lower-cased: GitHub logins are case-insensitive, so this keeps `acme/Widgets` and
    `acme/widgets` as one repository row instead of two. The allow-list comparison lower-cases
    for the same reason.
    """
    text = (value or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.removesuffix(".git").strip("/")
    parts = [part for part in text.split("/") if part]
    return "/".join(parts[-2:]).lower()


class RepositoryConnectRequest(BaseModel):
    """Body of `POST /api/v1/repositories/connect`."""

    repository: str = Field(
        description="The repository to connect, as `owner/name`.",
        examples=["fastapi/fastapi"],
    )

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str) -> str:
        normalized = _normalize_repository(value)
        if "/" not in normalized:
            raise ValueError("repository must be in the form 'owner/name'")
        owner, name = normalized.split("/", 1)
        if not owner or not name:
            raise ValueError("repository must be in the form 'owner/name'")
        return normalized


class RepositorySummary(BaseModel):
    """A repository row, as shown in lists."""

    id: int
    full_name: str = Field(examples=["fastapi/fastapi"])
    owner: str = Field(examples=["fastapi"])
    name: str = Field(examples=["fastapi"])
    default_branch: str | None = Field(default=None, examples=["main"])
    last_synced_at: TimestampOptional = None
    is_demo: bool = False

    model_config = {"from_attributes": True}


class LatestJobSummary(BaseModel):
    """The most recent ingestion job for a repository — enough to show sync state."""

    id: int
    status: str = Field(examples=["succeeded"])
    started_at: TimestampOptional = None
    finished_at: TimestampOptional = None
    resume_after: TimestampOptional = None
    counts: dict | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class RepositoryDetail(RepositorySummary):
    """A repository row plus its latest job, for the detail view."""

    latest_job: LatestJobSummary | None = None


class ConnectResponse(BaseModel):
    """The accepted-connect reply. The job runs asynchronously; poll `/jobs/{job_id}`."""

    job_id: int
    repository_id: int
    status: str = Field(examples=["pending"])
