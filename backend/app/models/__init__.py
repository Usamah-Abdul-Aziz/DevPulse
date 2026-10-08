"""Models. Tables are added phase by phase; see docs/architecture.md §4."""

from app.models.base import Base, TimestampMixin

__all__ = ["Base", "TimestampMixin"]
