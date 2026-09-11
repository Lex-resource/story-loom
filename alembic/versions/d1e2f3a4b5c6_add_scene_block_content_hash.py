"""add idempotency hash for scene blocks

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        'ALTER TABLE "novel_scene_blocks" '
        'ADD COLUMN IF NOT EXISTS "content_hash" VARCHAR(64)'
    ))
    op.execute(sa.text(
        'UPDATE novel_scene_blocks SET content_hash = md5(id::text) '
        'WHERE content_hash IS NULL'
    ))
    op.alter_column("novel_scene_blocks", "content_hash", nullable=False)
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_novel_scene_block_content_mainline" '
        'ON "novel_scene_blocks" ("project_id", "storyline_id", "scope_type", "scope_key", "content_hash") '
        'WHERE branch_id IS NULL'
    ))
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_novel_scene_block_content_branch" '
        'ON "novel_scene_blocks" ("project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "content_hash") '
        'WHERE branch_id IS NOT NULL'
    ))


def downgrade() -> None:
    op.drop_index("uq_novel_scene_block_content_branch", table_name="novel_scene_blocks")
    op.drop_index("uq_novel_scene_block_content_mainline", table_name="novel_scene_blocks")
    op.drop_column("novel_scene_blocks", "content_hash")
