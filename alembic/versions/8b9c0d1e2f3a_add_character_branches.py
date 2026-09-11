"""add independent character side-story branches

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from services.character_constants import (
    CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
    CHARACTER_BRANCH_DEFAULT_STATUS,
)


revision: str = "8b9c0d1e2f3a"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_branches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("arc_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("storyline_id", sa.String(length=100), nullable=False),
        sa.Column("anchor_main_chapter", sa.Integer(), nullable=False),
        sa.Column("current_chapter_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("target_chapters", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=20), server_default=CHARACTER_BRANCH_DEFAULT_STATUS, nullable=False),
        sa.Column("user_request", sa.Text(), server_default="", nullable=False),
        sa.Column("generation_config", sa.JSON(), nullable=False),
        sa.Column("anchor_context", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("auto_discovered", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["arc_id"], ["character_arcs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storyline_id", name="uq_character_branches_storyline"),
    )
    op.create_index("ix_character_branches_project_status", "character_branches", ["project_id", "status"])
    op.create_index("ix_character_branches_character_status", "character_branches", ["character_id", "status"])

    op.create_table(
        "character_branch_chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("anchor_main_chapter", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("outline", sa.JSON(), nullable=True),
        sa.Column("draft_content", sa.Text(), nullable=True),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("validator_result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT, nullable=False),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("relationship_changes", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["character_branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "chapter_index", name="uq_character_branch_chapter_position"),
    )
    op.create_index("ix_character_branch_chapters_branch_status", "character_branch_chapters", ["branch_id", "status"])


def downgrade() -> None:
    op.drop_table("character_branch_chapters")
    op.drop_table("character_branches")
