"""add candidate hash for idempotent memory atoms

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        'ALTER TABLE "novel_memory_atoms" '
        'ADD COLUMN IF NOT EXISTS "candidate_hash" VARCHAR(64)'
    ))
    # Existing rows predate candidate hashing. Their deterministic placeholder
    # is only used to satisfy the new non-null contract; new rows use SHA-256.
    op.execute(sa.text("UPDATE novel_memory_atoms SET candidate_hash = md5(id::text) WHERE candidate_hash IS NULL"))
    op.alter_column("novel_memory_atoms", "candidate_hash", nullable=False)
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_novel_memory_atom_candidate_mainline" '
        'ON "novel_memory_atoms" ("project_id", "storyline_id", "memory_key", "candidate_hash") '
        'WHERE branch_id IS NULL'
    ))
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_novel_memory_atom_candidate_branch" '
        'ON "novel_memory_atoms" ("project_id", "branch_id", "storyline_id", "memory_key", "candidate_hash") '
        'WHERE branch_id IS NOT NULL'
    ))


def downgrade() -> None:
    op.drop_index("uq_novel_memory_atom_candidate_branch", table_name="novel_memory_atoms")
    op.drop_index("uq_novel_memory_atom_candidate_mainline", table_name="novel_memory_atoms")
    op.drop_column("novel_memory_atoms", "candidate_hash")
