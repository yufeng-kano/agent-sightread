"""oauth grant redirect uri

Revision ID: 4c1f0a7d5e21
Revises: d19bd0ba1500
Create Date: 2026-08-20 21:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c1f0a7d5e21"
down_revision: str | None = "d19bd0ba1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("oauth_grants", sa.Column("redirect_uri", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_grants", "redirect_uri")
