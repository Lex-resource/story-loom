"""add deterministic narrative index projections"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "novel_narrative_index",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("storyline_id", sa.String(length=100), nullable=False, server_default="main"),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_chapter", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=True),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column("authority", sa.String(length=20), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("entry_key", sa.String(length=255), nullable=False),
        sa.Column("parent_key", sa.String(length=255), nullable=True),
        sa.Column("target_key", sa.String(length=255), nullable=True),
        sa.Column("relation", sa.String(length=50), nullable=False, server_default="contains"),
        sa.Column("chapter_index", sa.Integer(), nullable=True),
        sa.Column("chapter_end", sa.Integer(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="accepted"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["character_branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "entry_type IN ('story_event', 'story_segment', 'stage_summary', 'foreshadowing_link')",
            name="ck_narrative_index_entry_type",
        ),
        sa.CheckConstraint("status IN ('candidate', 'accepted')", name="ck_narrative_index_status"),
    )
    op.create_index(
        "uq_narrative_index_mainline", "novel_narrative_index",
        ["project_id", "storyline_id", "entry_type", "entry_key", "content_hash"],
        unique=True, postgresql_where=sa.text("branch_id IS NULL"),
    )
    op.create_index(
        "uq_narrative_index_branch", "novel_narrative_index",
        ["project_id", "branch_id", "storyline_id", "entry_type", "entry_key", "content_hash"],
        unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"),
    )
    op.create_index(
        "ix_narrative_index_recall", "novel_narrative_index",
        ["project_id", "branch_id", "storyline_id", "status", "chapter_index", "entry_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_narrative_index_recall", table_name="novel_narrative_index")
    op.drop_index("uq_narrative_index_branch", table_name="novel_narrative_index")
    op.drop_index("uq_narrative_index_mainline", table_name="novel_narrative_index")
    op.drop_table("novel_narrative_index")
