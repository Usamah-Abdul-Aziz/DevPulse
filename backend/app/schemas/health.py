"""Health and readiness response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response — the process is up and can answer requests."""

    status: str = Field(examples=["ok"])
    service: str = Field(examples=["devpulse-backend"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["local"])


class ReadinessComponent(BaseModel):
    name: str = Field(examples=["database"])
    status: str = Field(examples=["ok"])
    detail: str | None = Field(default=None)


class ReadinessResponse(BaseModel):
    """Readiness response — liveness plus dependency checks.

    The API answers 200 only when every dependency is reachable; otherwise 503
    with the failing component named, so a load balancer can route away.
    """

    status: str = Field(examples=["ok"])
    service: str = Field(examples=["devpulse-backend"])
    version: str = Field(examples=["0.1.0"])
    components: list[ReadinessComponent] = Field(default_factory=list)
