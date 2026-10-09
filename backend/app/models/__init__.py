"""Models. Tables are added phase by phase; see docs/architecture.md §4.

Phase 2 adds the ingestion tables: repositories, contributors, pull_requests,
pull_request_reviews, issues, file_changes, commits, releases, ingestion_jobs.
"""

from __future__ import annotations

from app.models.base import JSONB, Base, TimestampMixin
from app.models.commit import Commit
from app.models.contributor import GHOST_GITHUB_ID, Contributor
from app.models.ingestion_job import JOB_ACTIVE_STATES, JOB_TERMINAL_STATES, IngestionJob
from app.models.issue import Issue
from app.models.pull_request import FileChange, PullRequest, PullRequestReview
from app.models.release import Release
from app.models.repository import Repository

__all__ = [
    "GHOST_GITHUB_ID",
    "JOB_ACTIVE_STATES",
    "JOB_TERMINAL_STATES",
    "JSONB",
    "Base",
    "Commit",
    "Contributor",
    "FileChange",
    "IngestionJob",
    "Issue",
    "PullRequest",
    "PullRequestReview",
    "Release",
    "Repository",
    "TimestampMixin",
]
