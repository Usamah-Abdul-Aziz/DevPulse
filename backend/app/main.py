"""FastAPI application factory.

Wiring order matters: logging first, then CORS, then routers, then the root
health shortcut. Importing models here ensures Alembic sees them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.models import Base  # noqa: F401  (registered for Alembic autogenerate)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="DevPulse API",
        description=(
            "Read API + async ingestion for the DevPulse engineering-intelligence "
            "platform. See /docs for the interactive schema."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    # Convenience root alias so `/healthz` works without the version prefix.
    app.include_router(health_router)

    return app


app = create_app()
