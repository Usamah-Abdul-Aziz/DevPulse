"""Integration tests — run against a real Postgres (CI service container).

Run locally: RUN_INTEGRATION=1 DATABASE_URL=postgresql://... pytest -m integration
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_readyz_passes_against_real_postgres(client: TestClient) -> None:
    """The readiness probe's database check works against real Postgres."""
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {c["name"]: c["status"] for c in body["components"]}["database"] == "ok"


def test_session_can_execute_a_real_query(db_session: object) -> None:
    """The SQLAlchemy session factory is wired to the configured database."""
    result = db_session.execute(text("SELECT 42 AS answer")).scalar_one()
    assert result == 42
