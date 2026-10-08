"""Configuration tests — CORS origin parsing and list splitting."""

from __future__ import annotations

from app.core.config import Settings


def test_default_origins_include_local_frontend() -> None:
    settings = Settings(frontend_origin="http://localhost:3000")
    assert settings.cors_origins == ["http://localhost:3000"]


def test_multiple_origins_are_split_and_trimmed() -> None:
    settings = Settings(frontend_origin=" https://a.example ,https://b.example ")
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_allowed_repos_parses_comma_string() -> None:
    settings = Settings(allowed_repos="fastapi/fastapi, pallets/flask")
    assert settings.allowed_repos == ["fastapi/fastapi", "pallets/flask"]


def test_empty_allowed_repos_stays_empty() -> None:
    assert Settings(allowed_repos="").allowed_repos == []
    assert Settings(allowed_repos=None).allowed_repos == []
