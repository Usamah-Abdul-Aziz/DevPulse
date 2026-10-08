"""API v1 router. Feature routers are mounted here as phases land."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)

# Phase 2: ingestion routers (POST /repositories/connect, GET /jobs/{id})
# Phase 3: analytics routers (metrics, activity, health, contributors)
# Phase 8: risk routers (pull-requests, risks)
