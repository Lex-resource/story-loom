"""add recall hit stats and scene block consolidation audit

Revision ID: b3c4d5e6f7a8
Revises: f7b8c9d0e1a2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "f7b8c9d0e1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "novel_memory_atoms",
        sa.Column("recall_use_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "novel_memory_atoms",
        sa.Column("last_recalled_chapter", sa.Integer(), nullable=True),
    )
    op.add_column(
        "novel_scene_blocks",
        sa.Column("consolidation_diff", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("novel_scene_blocks", "consolidation_diff")
    op.drop_column("novel_memory_atoms", "last_recalled_chapter")
    op.drop_column("novel_memory_atoms", "recall_use_count")
