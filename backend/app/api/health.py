"""Health endpoints.

`/healthz` is liveness (process up). `/readyz` is readiness (dependencies
reachable). Keeping them separate lets Render's health check distinguish "cold
starting" from "broken" — see ADR-007.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings
from app.core.database import get_db
from app.schemas.health import HealthResponse, ReadinessComponent, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe. Never touches dependencies."""
    return HealthResponse(
        status="ok",
        service="devpulse-backend",
        version=__version__,
        environment=settings.environment,
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={503: {"model": ReadinessResponse}},
)
def readyz(db: Session = Depends(get_db)) -> ReadinessResponse:
    """Readiness probe. Fails loudly with the component that is broken."""
    components: list[ReadinessComponent] = []

    db_ok = True
    try:
        db.execute(text("SELECT 1"))
        components.append(ReadinessComponent(name="database", status="ok"))
    except SQLAlchemyError as exc:
        db_ok = False
        components.append(ReadinessComponent(name="database", status="fail", detail=str(exc)[:200]))

    if not db_ok:
        return ReadinessResponse(
            status="fail",
            service="devpulse-backend",
            version=__version__,
            components=components,
        )

    return ReadinessResponse(
        status="ok",
        service="devpulse-backend",
        version=__version__,
        components=components,
    )
