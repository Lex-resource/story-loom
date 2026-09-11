"""add durable hard-conflict queue for layered novel memory

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "novel_memory_conflicts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Uuid(), sa.ForeignKey("character_branches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("storyline_id", sa.String(length=100), server_default="main", nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_chapter", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=True),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column("authority", sa.String(length=20), server_default="generated", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("conflict_hash", sa.String(length=64), nullable=False),
        sa.Column("conflict_type", sa.String(length=50), nullable=False),
        sa.Column("memory_key", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), server_default="high", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), server_default="", nullable=False),
        sa.Column("conflicts_with", sa.Text(), server_default="", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_novel_memory_conflict_status",
        ),
    )
    op.create_index(
        "uq_novel_memory_conflict_hash",
        "novel_memory_conflicts",
        ["conflict_hash"],
        unique=True,
    )
    op.create_index(
        "ix_novel_memory_conflicts_queue",
        "novel_memory_conflicts",
        ["project_id", "branch_id", "storyline_id", "status", "source_chapter"],
    )


def downgrade() -> None:
    op.drop_index("ix_novel_memory_conflicts_queue", table_name="novel_memory_conflicts")
    op.drop_index("uq_novel_memory_conflict_hash", table_name="novel_memory_conflicts")
    op.drop_table("novel_memory_conflicts")
