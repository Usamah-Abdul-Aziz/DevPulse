"""Fixtures for ingestion tests: a repository row and a pipeline wired to the fake client.

Table isolation between tests lives in the top-level `tests/conftest.py` and is shared by every
test module, so it is not repeated here.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.pipeline import IngestionCursor, IngestionPipeline
from app.models import Repository
from tests.ingestion.fake_github import FakeGitHubClient, now


def make_settings(**overrides: object) -> Settings:
    """Settings with a wide window and no rate-limit interference, unless overridden."""
    defaults: dict[str, object] = {
        "ingestion_history_months": 24,
        "ingestion_page_size": 100,
        "ingestion_min_rate_budget": 1,
        "ingestion_max_file_changes_per_pr": 1000,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def make_repository(db_session: Session, *, last_synced_at: datetime | None = None) -> Repository:
    repo = Repository(
        owner="acme",
        name="widgets",
        full_name="acme/widgets",
        default_branch="main",
        last_synced_at=last_synced_at,
    )
    db_session.add(repo)
    db_session.commit()
    return repo


def run_pipeline(
    db_session: Session,
    client: FakeGitHubClient,
    repository: Repository,
    *,
    settings: Settings | None = None,
    cursor: IngestionCursor | None = None,
) -> tuple[IngestionPipeline, IngestionCursor]:
    """Run the pipeline against the fake client and return (pipeline, final cursor)."""
    pipeline = IngestionPipeline(
        db_session,
        client,  # type: ignore[arg-type]  # the fake implements the same protocol
        repository,
        settings=settings or make_settings(),
        cursor=cursor,
    )
    returned = pipeline.run()
    return pipeline, returned


@pytest.fixture()
def now_dt() -> datetime:
    return now()
