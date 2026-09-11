"""add project character branch discovery setting

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c0d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "8b9c0d1e2f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "novels",
        sa.Column("character_branch_auto_discovery_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("novels", "character_branch_auto_discovery_enabled")
