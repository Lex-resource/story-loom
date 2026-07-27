"""add pipeline and knowledge data

Revision ID: 7f8c3e5d4a21
Revises: 2d0e08d9a7b2
Create Date: 2026-06-20 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f8c3e5d4a21"
down_revision: Union[str, Sequence[str], None] = "2d0e08d9a7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "chapters" in tables and not _has_column(inspector, "chapters", "pipeline_step"):
        op.add_column("chapters", sa.Column("pipeline_step", sa.String(length=50), nullable=True))
    if "settings_docs" in tables and not _has_column(inspector, "settings_docs", "data"):
        op.add_column("settings_docs", sa.Column("data", sa.JSON(), nullable=True))
    if "jobs" in tables and not _has_column(inspector, "jobs", "params"):
        op.add_column("jobs", sa.Column("params", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "jobs" in tables and _has_column(inspector, "jobs", "params"):
        op.drop_column("jobs", "params")
    if "settings_docs" in tables and _has_column(inspector, "settings_docs", "data"):
        op.drop_column("settings_docs", "data")
    if "chapters" in tables and _has_column(inspector, "chapters", "pipeline_step"):
        op.drop_column("chapters", "pipeline_step")


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))
