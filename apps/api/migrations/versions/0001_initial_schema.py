"""initial schema

Revision ID: d19bd0ba1500
Revises:
Create Date: 2026-08-20 18:14:12.575165
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d19bd0ba1500"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("pages_spec", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.Integer(), nullable=False),
        sa.Column("bbox_format", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("pages_done", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_jobs_dedup",
        "jobs",
        [
            "user_id",
            "sha256",
            "model",
            "profile",
            "profile_version",
            "pages_spec",
            "pipeline_version",
        ],
        unique=False,
        postgresql_where=sa.text("status = 'succeeded'"),
    )
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"], unique=False)
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)
    op.create_table(
        "oauth_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("pkce_challenge", sa.String(length=128), nullable=True),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "openrouter_keys",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("masked", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("default_model", sa.String(length=255), nullable=True),
        sa.Column("default_profile", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "job_pages",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "page_no"),
    )
    op.create_table(
        "results",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("pages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("figures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_table(
        "usage_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_usage_log_user_created", "usage_log", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_usage_log_user_created", table_name="usage_log")
    op.drop_table("usage_log")
    op.drop_table("results")
    op.drop_table("job_pages")
    op.drop_table("user_settings")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("openrouter_keys")
    op.drop_table("oauth_grants")
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_index(
        "ix_jobs_dedup", table_name="jobs", postgresql_where=sa.text("status = 'succeeded'")
    )
    op.drop_table("jobs")
    op.drop_index(op.f("ix_api_keys_user_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("oauth_clients")
