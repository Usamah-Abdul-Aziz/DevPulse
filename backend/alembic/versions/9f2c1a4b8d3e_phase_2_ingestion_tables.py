"""phase 2 ingestion tables

Revision ID: 9f2c1a4b8d3e
Revises: 8dd3000d3f1b
Create Date: 2026-10-09 09:30:00.000000

Hand-written to stay dialect-portable: the JSON columns use `app.models.base.JSONB`, which renders
as JSONB on Postgres and JSON on SQLite (unit tests). Verified against the models by
`tests/test_migrations.py`.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.base import JSONB

revision: str = "9f2c1a4b8d3e"
down_revision: Union[str, None] = "8dd3000d3f1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # repositories ---------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(511), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
    )
    op.create_index("ix_repositories_last_synced_at", "repositories", ["last_synced_at"])

    # contributors ----------------------------------------------------------
    op.create_table(
        "contributors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_id", sa.String(64), nullable=False),
        sa.Column("login", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_ghost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "github_id", name="uq_contributors_repo_github_id"),
    )
    op.create_index("ix_contributors_repository_id_login", "contributors", ["repository_id", "login"])

    # pull_requests ---------------------------------------------------------
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("contributors.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("changed_files", sa.Integer(), nullable=True),
        sa.Column("base_branch", sa.String(255), nullable=True),
        sa.Column("head_branch", sa.String(255), nullable=True),
        sa.Column("labels", JSONB(), nullable=True),
        sa.Column("truncated_files", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_payload", JSONB(), nullable=True),
        sa.UniqueConstraint("repository_id", "number", name="uq_pull_requests_repo_number"),
    )
    op.create_index("ix_pull_requests_repo_created_at", "pull_requests", ["repository_id", "created_at"])
    op.create_index("ix_pull_requests_repo_updated_at", "pull_requests", ["repository_id", "updated_at"])

    # pull_request_reviews ---------------------------------------------------
    op.create_table(
        "pull_request_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_id", sa.String(64), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("contributors.id"), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("pull_request_id", "github_id", name="uq_reviews_pr_github_id"),
    )
    op.create_index(
        "ix_reviews_pr_submitted_at", "pull_request_reviews", ["pull_request_id", "submitted_at"]
    )

    # issues ----------------------------------------------------------------
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("contributors.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels", JSONB(), nullable=True),
        sa.Column("reopened_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body", sa.Text(), nullable=True),
        sa.UniqueConstraint("repository_id", "number", name="uq_issues_repo_number"),
    )
    op.create_index("ix_issues_repo_created_at", "issues", ["repository_id", "created_at"])
    op.create_index("ix_issues_repo_updated_at", "issues", ["repository_id", "updated_at"])

    # commits ---------------------------------------------------------------
    op.create_table(
        "commits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sha", sa.String(40), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("contributors.id"), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("author_email", sa.String(255), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("is_merge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("message", sa.Text(), nullable=True),
        sa.UniqueConstraint("repository_id", "sha", name="uq_commits_repo_sha"),
    )
    op.create_index("ix_commits_repo_committed_at", "commits", ["repository_id", "committed_at"])

    # releases --------------------------------------------------------------
    op.create_table(
        "releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("contributors.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("repository_id", "tag", name="uq_releases_repo_tag"),
    )
    op.create_index("ix_releases_repo_published_at", "releases", ["repository_id", "published_at"])

    # file_changes (after commits: its `commit_id` FK points here) -----------
    op.create_table(
        "file_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("commit_id", sa.Integer(), sa.ForeignKey("commits.id"), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("pull_request_id", "path", name="uq_file_changes_pr_path"),
    )
    op.create_index("ix_file_changes_pr_path", "file_changes", ["pull_request_id", "path"])

    # ingestion_jobs --------------------------------------------------------
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("counts", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'succeeded', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
    )
    op.create_index("ix_ingestion_jobs_repo_started_at", "ingestion_jobs", ["repository_id", "started_at"])


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_table("file_changes")
    op.drop_table("releases")
    op.drop_table("commits")
    op.drop_table("issues")
    op.drop_table("pull_request_reviews")
    op.drop_table("pull_requests")
    op.drop_table("contributors")
    op.drop_table("repositories")
