"""add character card domain and materialized manifests

Revision ID: 7a8b9c0d1e2f
Revises: f2c3d4e5f6a7
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from services.character_constants import (
    CHARACTER_ARC_DEFAULT_STATUS,
    CHARACTER_ARC_DEFAULT_TYPE,
    CHARACTER_FIRST_CHAPTER,
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    CHARACTER_RELATIONSHIP_ACTIVE,
    CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
    CHARACTER_STORYLINE_MAIN,
)


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "f2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("card_data", sa.JSON(), nullable=False),
        sa.Column("current_state", sa.JSON(), nullable=False),
        sa.Column("importance", sa.String(length=20), server_default=CHARACTER_GENERATION_DEFAULT_IMPORTANCE, nullable=False),
        sa.Column("last_appearance", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=CHARACTER_GENERATION_DEFAULT_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_character_cards_project_name"),
    )
    op.create_index("ix_character_cards_project_importance", "character_cards", ["project_id", "importance"])
    op.create_index("ix_character_cards_project_status", "character_cards", ["project_id", "status"])

    op.create_table(
        "character_card_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("card_data", sa.JSON(), nullable=False),
        sa.Column("current_state", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_card_snapshots_character_created", "character_card_snapshots", ["character_id", "created_at"])

    op.create_table(
        "character_card_change_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("before_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("patch", sa.JSON(), nullable=False),
        sa.Column("effective_from_chapter", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["before_snapshot_id"], ["character_card_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("before_snapshot_id", name="uq_character_card_change_before_snapshot"),
    )
    op.create_index("ix_character_card_changes_character_created", "character_card_change_records", ["character_id", "created_at"])

    op.create_table(
        "character_chapter_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("storyline_id", sa.String(length=100), server_default=CHARACTER_STORYLINE_MAIN, nullable=False),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "storyline_id", "chapter_index", name="uq_character_chapter_state_position"),
    )
    op.create_index("ix_character_chapter_states_lookup", "character_chapter_states", ["character_id", "storyline_id", "chapter_index"])

    op.create_table(
        "character_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_character_id", sa.Uuid(), nullable=False),
        sa.Column("target_character_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=100), server_default=CHARACTER_RELATIONSHIP_DEFAULT_TYPE, nullable=False),
        sa.Column("status", sa.String(length=20), server_default=CHARACTER_RELATIONSHIP_ACTIVE, nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("valid_from_chapter", sa.Integer(), server_default=str(CHARACTER_FIRST_CHAPTER), nullable=False),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_relationships_project_source", "character_relationships", ["project_id", "source_character_id"])
    op.create_index("ix_character_relationships_project_target", "character_relationships", ["project_id", "target_character_id"])

    op.create_table(
        "character_arcs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("storyline_id", sa.String(length=100), server_default=CHARACTER_STORYLINE_MAIN, nullable=False),
        sa.Column("arc_type", sa.String(length=20), server_default=CHARACTER_ARC_DEFAULT_TYPE, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("anchor_chapter", sa.Integer(), nullable=True),
        sa.Column("target_chapter", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=CHARACTER_ARC_DEFAULT_STATUS, nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_arcs_character_storyline", "character_arcs", ["character_id", "storyline_id"])

    op.create_table(
        "character_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("is_read_only", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["character_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["novels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", name="uq_character_manifests_character"),
    )
    op.create_index("ix_character_manifests_project_updated", "character_manifests", ["project_id", "updated_at"])


def downgrade() -> None:
    op.drop_table("character_manifests")
    op.drop_table("character_arcs")
    op.drop_table("character_relationships")
    op.drop_table("character_chapter_states")
    op.drop_table("character_card_change_records")
    op.drop_table("character_card_snapshots")
    op.drop_table("character_cards")
