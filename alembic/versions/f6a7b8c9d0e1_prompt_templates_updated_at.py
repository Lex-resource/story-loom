"""prompt_templates.updated_at for cross-process cache stamping

Revision ID: f6a7b8c9d0e1
Revises: d4a5b6c7e8f9
Create Date: 2026-08-29

组合版本戳 (COUNT(*), MAX(updated_at)) 依赖本列（services/config_versions.py）。
回填用 created_at，让存量行的"最后修改时间"等于创建时间而不是迁移时刻。
列风格与全库一致（nullable、无 server_default —— 默认值由 ORM 的
default/onupdate 在 Python 侧供给），否则 alembic check 会报漂移。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "d4a5b6c7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prompt_templates", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE prompt_templates SET updated_at = created_at")


def downgrade() -> None:
    op.drop_column("prompt_templates", "updated_at")
