"""Repository model.

The root entity of the data model: every other table is scoped to a row here. Ingestion creates
or updates a row per `(owner, name)`; `is_demo` marks the pre-ingested repository that Demo Mode
points at (Section 19 of the blueprint).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
        Index("ix_repositories_last_synced_at", "last_synced_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    #: GitHub login of the org or user, e.g. "fastapi".
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Repository name, e.g. "fastapi".
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: `owner/name`, stored so list ordering and display never reparse the two columns.
    full_name: Mapped[str] = mapped_column(String(511), nullable=False)

    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: True for the pre-ingested demo repository (ADR-003).
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    pull_requests = relationship(
        "PullRequest", back_populates="repository", cascade="all, delete-orphan"
    )
    issues = relationship("Issue", back_populates="repository", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="repository", cascade="all, delete-orphan")
    releases = relationship("Release", back_populates="repository", cascade="all, delete-orphan")
    contributors = relationship(
        "Contributor", back_populates="repository", cascade="all, delete-orphan"
    )
    ingestion_jobs = relationship(
        "IngestionJob", back_populates="repository", cascade="all, delete-orphan"
    )
