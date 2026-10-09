"""Shared pytest fixtures.

Unit tests use an in-memory SQLite engine so they need no external services.
Integration tests (RUN_INTEGRATION=1) use the configured DATABASE_URL so they
exercise real Postgres behaviour.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings, settings
from app.core.database import get_db
from app.main import create_app
from app.models import Base


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _make_engine() -> Engine:
    """In-memory SQLite for unit tests; the configured DB for integration tests."""
    if _integration_enabled():
        return create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Session-scoped engine: in-memory SQLite for unit tests, the configured
    DATABASE_URL for integration tests (RUN_INTEGRATION=1)."""
    test_engine = _make_engine()
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)


@pytest.fixture()
def client(engine: Engine) -> Iterator[TestClient]:
    """API client backed by the session-scoped engine."""
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = create_app()

    def override_get_db() -> Iterator[Session]:
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(engine: Engine) -> Iterator[Session]:
    """Raw SQLAlchemy session on the same engine as `client`."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _isolate_tables(db_session: Session) -> Iterator[None]:
    """Wipe every table after each test.

    The engine is session-scoped (in-memory SQLite shares one connection across tests), so without
    this, rows from one test would satisfy another test's unique constraints and its `count()`
    expectations. Children are deleted before parents.
    """
    yield
    # Roll back first: a test may leave a dirty ORM object in the identity map, and deleting its
    # row underneath it makes the following flush raise `StaleDataError`.
    db_session.rollback()
    for model in reversed(Base.metadata.sorted_tables):
        db_session.execute(model.delete())
    db_session.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Ensure get_settings() cache is reset between tests that patch env."""
    yield
    get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly enabled (RUN_INTEGRATION=1)."""
    enabled = os.environ.get("RUN_INTEGRATION") == "1"
    skip_marker = pytest.mark.skip(reason="set RUN_INTEGRATION=1 with a live DATABASE_URL")
    for item in items:
        if "integration" in item.keywords and not enabled:
            item.add_marker(skip_marker)
