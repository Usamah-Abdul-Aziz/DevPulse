"""API v1 router. Feature routers are mounted here as phases land."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.repositories import router as repositories_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(repositories_router)
api_router.include_router(jobs_router)

# Phase 3: analytics routers (metrics, activity, health, contributors)
# Phase 8: risk routers (pull-requests, risks)
