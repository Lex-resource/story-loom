"""fix nullable branch uniqueness for novel memory scopes

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # a1b2c3d4e5f6 was initially created with ordinary UNIQUE constraints.
    # Drop them when present so NULL branch_id cannot bypass idempotency.
    for table, constraint in (
        ("novel_memory_evidence", "uq_novel_memory_evidence_content"),
        ("novel_memory_atoms", "uq_novel_memory_atom_version"),
        ("novel_scene_blocks", "uq_novel_scene_block_version"),
        ("project_doctrines", "uq_project_doctrine_version"),
    ):
        op.execute(sa.text(
            f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"'
        ))

    indexes = (
        ("uq_novel_memory_evidence_mainline", "novel_memory_evidence", ["project_id", "storyline_id", "source_ref", "content_hash"], "branch_id IS NULL"),
        ("uq_novel_memory_evidence_branch", "novel_memory_evidence", ["project_id", "branch_id", "storyline_id", "source_ref", "content_hash"], "branch_id IS NOT NULL"),
        ("uq_novel_memory_atom_mainline", "novel_memory_atoms", ["project_id", "storyline_id", "memory_key", "version"], "branch_id IS NULL"),
        ("uq_novel_memory_atom_branch", "novel_memory_atoms", ["project_id", "branch_id", "storyline_id", "memory_key", "version"], "branch_id IS NOT NULL"),
        ("uq_novel_scene_block_mainline", "novel_scene_blocks", ["project_id", "storyline_id", "scope_type", "scope_key", "version"], "branch_id IS NULL"),
        ("uq_novel_scene_block_branch", "novel_scene_blocks", ["project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "version"], "branch_id IS NOT NULL"),
        ("uq_project_doctrine_mainline", "project_doctrines", ["project_id", "storyline_id", "doctrine_key", "version"], "branch_id IS NULL"),
        ("uq_project_doctrine_branch", "project_doctrines", ["project_id", "branch_id", "storyline_id", "doctrine_key", "version"], "branch_id IS NOT NULL"),
    )
    for name, table, columns, predicate in indexes:
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        op.execute(sa.text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" '
            f'ON "{table}" ({quoted_columns}) WHERE {predicate}'
        ))


def downgrade() -> None:
    # Keep the corrected indexes when returning to a1b2c3d4e5f6; that revision
    # now defines the same partial-unique schema for clean installations.
    pass
