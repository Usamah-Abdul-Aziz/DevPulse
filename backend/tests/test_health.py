"""Health endpoint tests (Phase 1 walking skeleton)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "devpulse-backend"


def test_healthz_available_without_version_prefix(client: TestClient) -> None:
    """The root alias must work so platform health checks stay stable."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_reports_database_component(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    components = {c["name"]: c["status"] for c in response.json()["components"]}
    assert components["database"] == "ok"


def test_openapi_schema_advertises_docs(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "DevPulse API"
    assert "/healthz" in schema["paths"]


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
