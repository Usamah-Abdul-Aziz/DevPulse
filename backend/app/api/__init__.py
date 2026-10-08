"""API layer. Routers only — business logic lives in app/services."""

from app.api.router import api_router

__all__ = ["api_router"]
