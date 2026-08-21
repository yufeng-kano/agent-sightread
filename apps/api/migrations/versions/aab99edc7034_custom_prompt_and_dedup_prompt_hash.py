"""custom prompt and dedup prompt hash

Revision ID: aab99edc7034
Revises: a4f19d166a63
Create Date: 2026-08-21 20:18:13.831951
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aab99edc7034"
down_revision: str | None = "a4f19d166a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    op.drop_index("ix_jobs_dedup", table_name="jobs")
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
            "prompt_sha256",
            "pipeline_version",
        ],
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_dedup", table_name="jobs")
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
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )
    op.drop_column("jobs", "prompt_sha256")
    op.drop_column("jobs", "prompt")
    op.drop_column("user_settings", "system_prompt")
