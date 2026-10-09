"""Contributor model.

Contributors are keyed by GitHub's node `github_id`, not by login: logins are mutable (a user can
rename an account), so keying on login would silently split one person into two rows after a
rename. See ADR-010.

`is_bot` flags the accounts excluded from contributor and workload metrics (blueprint §6.1).
`is_ghost` marks placeholder rows standing in for deleted accounts, whose identities GitHub no
longer returns; they are kept for referential integrity and excluded from people metrics.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

#: Node id used when GitHub returns no author for an item (deleted account).
GHOST_GITHUB_ID = "GHOST"


class Contributor(Base, TimestampMixin):
    __tablename__ = "contributors"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_contributors_repo_github_id"),
        Index("ix_contributors_repository_id_login", "repository_id", "login"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    #: Stable GraphQL node id, e.g. "MDQ6VXNlcjEzNjQ5MzI=".
    github_id: Mapped[str] = mapped_column(String(64), nullable=False)
    login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_bot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_ghost: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    repository = relationship("Repository", back_populates="contributors")
