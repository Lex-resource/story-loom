"""runtime_tunables table: DB-backed runtime tunables

Revision ID: f7b8c9d0e1a2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-29

键值存储,不 seed 默认行 —— 缺行时 services/runtime_tunables_service 的
typed getter 回落 PARAM_SPECS 默认值。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7b8c9d0e1a2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_tunables",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # 与全库一致：nullable、无 server_default，默认值由 ORM 供给
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("runtime_tunables")
