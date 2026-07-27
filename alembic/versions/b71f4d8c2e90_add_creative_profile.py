"""Add creative profile to novels.

Revision ID: b71f4d8c2e90
Revises: c4f8b2d91a63
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b71f4d8c2e90"
down_revision: Union[str, Sequence[str], None] = "c4f8b2d91a63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("novels", sa.Column("creative_profile", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("novels", "creative_profile")
