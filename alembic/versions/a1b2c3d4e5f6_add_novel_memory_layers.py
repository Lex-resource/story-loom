"""add layered novel memory tables

Revision ID: a1b2c3d4e5f6
Revises: 9c0d1e2f3a4b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9c0d1e2f3a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_columns():
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "novel_memory_evidence",
        *_common_columns(),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("extracted_data", sa.JSON(), nullable=True),
        sa.Column("is_immutable", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("uq_novel_memory_evidence_mainline", "novel_memory_evidence", ["project_id", "storyline_id", "source_ref", "content_hash"], unique=True, postgresql_where=sa.text("branch_id IS NULL"))
    op.create_index("uq_novel_memory_evidence_branch", "novel_memory_evidence", ["project_id", "branch_id", "storyline_id", "source_ref", "content_hash"], unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"))
    op.create_index("ix_novel_memory_evidence_scope_chapter", "novel_memory_evidence", ["project_id", "branch_id", "storyline_id", "source_chapter"])

    op.create_table(
        "novel_memory_atoms",
        *_common_columns(),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("novel_memory_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("memory_key", sa.String(length=255), nullable=False),
        sa.Column("atom_type", sa.String(length=50), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="candidate", nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_novel_memory_atom_confidence"),
        sa.CheckConstraint("status IN ('candidate', 'accepted', 'rejected', 'superseded')", name="ck_novel_memory_atom_status"),
        sa.CheckConstraint("authority IN ('generated', 'user', 'published', 'system')", name="ck_novel_memory_atom_authority"),
    )
    op.create_index("uq_novel_memory_atom_mainline", "novel_memory_atoms", ["project_id", "storyline_id", "memory_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NULL"))
    op.create_index("uq_novel_memory_atom_branch", "novel_memory_atoms", ["project_id", "branch_id", "storyline_id", "memory_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"))
    op.create_index("ix_novel_memory_atoms_recall", "novel_memory_atoms", ["project_id", "branch_id", "storyline_id", "status", "valid_from_chapter"])

    op.create_table(
        "novel_scene_blocks",
        *_common_columns(),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("current_state", sa.JSON(), nullable=False),
        sa.Column("open_questions", sa.JSON(), nullable=False),
        sa.Column("recent_changes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_novel_scene_block_confidence"),
    )
    op.create_index("uq_novel_scene_block_mainline", "novel_scene_blocks", ["project_id", "storyline_id", "scope_type", "scope_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NULL"))
    op.create_index("uq_novel_scene_block_branch", "novel_scene_blocks", ["project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"))
    op.create_index("uq_novel_scene_block_content_mainline", "novel_scene_blocks", ["project_id", "storyline_id", "scope_type", "scope_key", "content_hash"], unique=True, postgresql_where=sa.text("branch_id IS NULL"))
    op.create_index("uq_novel_scene_block_content_branch", "novel_scene_blocks", ["project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "content_hash"], unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"))
    op.create_index("ix_novel_scene_blocks_recall", "novel_scene_blocks", ["project_id", "branch_id", "storyline_id", "scope_type", "valid_to_chapter"])

    op.create_table(
        "project_doctrines",
        *_common_columns(),
        sa.Column("doctrine_key", sa.String(length=255), nullable=False),
        sa.Column("doctrine_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_project_doctrine_confidence"),
    )
    op.create_index("uq_project_doctrine_mainline", "project_doctrines", ["project_id", "storyline_id", "doctrine_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NULL"))
    op.create_index("uq_project_doctrine_branch", "project_doctrines", ["project_id", "branch_id", "storyline_id", "doctrine_key", "version"], unique=True, postgresql_where=sa.text("branch_id IS NOT NULL"))
    op.create_index("ix_project_doctrines_recall", "project_doctrines", ["project_id", "branch_id", "storyline_id", "doctrine_type"])


def downgrade() -> None:
    op.drop_index("ix_project_doctrines_recall", table_name="project_doctrines")
    op.drop_index("uq_project_doctrine_branch", table_name="project_doctrines")
    op.drop_index("uq_project_doctrine_mainline", table_name="project_doctrines")
    op.drop_table("project_doctrines")
    op.drop_index("ix_novel_scene_blocks_recall", table_name="novel_scene_blocks")
    op.drop_index("uq_novel_scene_block_branch", table_name="novel_scene_blocks")
    op.drop_index("uq_novel_scene_block_mainline", table_name="novel_scene_blocks")
    op.drop_index("uq_novel_scene_block_content_branch", table_name="novel_scene_blocks")
    op.drop_index("uq_novel_scene_block_content_mainline", table_name="novel_scene_blocks")
    op.drop_table("novel_scene_blocks")
    op.drop_index("ix_novel_memory_atoms_recall", table_name="novel_memory_atoms")
    op.drop_index("uq_novel_memory_atom_branch", table_name="novel_memory_atoms")
    op.drop_index("uq_novel_memory_atom_mainline", table_name="novel_memory_atoms")
    op.drop_table("novel_memory_atoms")
    op.drop_index("ix_novel_memory_evidence_scope_chapter", table_name="novel_memory_evidence")
    op.drop_index("uq_novel_memory_evidence_branch", table_name="novel_memory_evidence")
    op.drop_index("uq_novel_memory_evidence_mainline", table_name="novel_memory_evidence")
    op.drop_table("novel_memory_evidence")
