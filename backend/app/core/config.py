"""Application configuration.

All settings come from environment variables (see `.env.example`). Secrets are
never hard-coded — see AGENTS.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ------------------------------------------------------
    environment: Literal["local", "test", "staging", "production"] = Field(default="local")
    debug: bool = Field(default=False)

    # --- Database ---------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://devpulse:devpulse@localhost:5432/devpulse"
    )
    test_database_url: str | None = Field(default=None)

    # --- GitHub -----------------------------------------------------------
    github_token: str | None = Field(default=None)

    # --- App --------------------------------------------------------------
    secret_key: str = Field(default="change-me")
    allowed_repos: list[str] = Field(default_factory=list)
    frontend_origin: str = Field(default="http://localhost:3000")

    @field_validator("allowed_repos", mode="before")
    @classmethod
    def _split_comma_list(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [repo.strip() for repo in value.split(",") if repo.strip()]
        if value is None:
            return []
        return list(value)

    @property
    def cors_origins(self) -> list[str]:
        origins = {origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()}
        return sorted(origins)

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached because pydantic-settings re-parses env on every call, and this is
    called per-request via FastAPI's dependency injection.
    """
    return Settings()


settings = get_settings()
