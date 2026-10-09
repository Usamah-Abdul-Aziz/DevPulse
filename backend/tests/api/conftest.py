"""API test fixtures: a `TestClient` with settings and the runner injected.

The runner is a FastAPI dependency precisely so tests can swap in a synchronous one — a real
`BackgroundTasks` job would outlive the test and hit the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.ingestion.runner import IngestionRunner, get_ingestion_runner
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings that allow one repository and carry a dummy token, unless overridden."""
    defaults: dict[str, object] = {
        "environment": "test",
        "github_token": "test-token",
        "allowed_repos": ["acme/widgets", "acme/gadgets"],
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class RecordingRunner(IngestionRunner):
    """A runner that records job ids and runs synchronously, with no GitHub traffic."""

    def __init__(self, session_factory: sessionmaker, **kwargs: Any) -> None:
        super().__init__(session_factory, **kwargs)
        self.job_ids: list[int] = []

    def __call__(self, job_id: int) -> None:
        self.job_ids.append(job_id)


@pytest.fixture()
def make_client(db_session: Session) -> Iterator[Any]:
    """Build a `TestClient` with injected settings and an optional runner override."""
    created: list[TestClient] = []

    def _make(
        *,
        settings: Settings | None = None,
        runner: IngestionRunner | None = None,
    ) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db] = _override_get_db(db_session)
        if settings is not None:
            app.dependency_overrides[get_settings] = lambda: settings
        if runner is not None:
            app.dependency_overrides[get_ingestion_runner] = lambda: runner

        # Keep the app factory's own exception wiring; `create_app` already registers it.
        client = TestClient(app)
        created.append(client)
        return client

    yield _make


def _override_get_db(db_session: Session) -> Any:
    def override() -> Iterator[Session]:
        yield db_session

    return override
