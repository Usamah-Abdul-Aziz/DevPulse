"""Release model (REST `/releases`).

Releases back the "Deployment frequency" DORA proxy (blueprint §6.4). Draft releases have a null
`published_at` and are dropped at load time — a draft is an intent, not a release.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Release(Base):
    """Release (REST `/releases`).

    No `TimestampMixin`: `published_at` is the release's own time and the only one analytics uses.

    Releases back the "Deployment frequency" DORA proxy (blueprint §6.4). Draft releases have a null
    `published_at` and are dropped at load time — a draft is an intent, not a release.
    """

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("repository_id", "tag", name="uq_releases_repo_tag"),
        Index("ix_releases_repo_published_at", "repository_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    tag: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository", back_populates="releases")
    author = relationship("Contributor", foreign_keys=[author_id])
