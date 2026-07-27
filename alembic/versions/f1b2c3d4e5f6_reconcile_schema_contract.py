"""reconcile schema contract

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-23 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE settings_docs "
            "SET data = CAST('{}' AS JSON) "
            "WHERE data IS NULL"
        )
    )
    op.alter_column(
        "settings_docs",
        "data",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "settings_docs",
        "data",
        existing_type=sa.JSON(),
        nullable=True,
    )
