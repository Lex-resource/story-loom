"""Enable chapter-content knowledge extraction for short stories.

Revision ID: c4f8b2d91a63
Revises: a59471799ea7
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8b2d91a63"
down_revision: Union[str, Sequence[str], None] = "a59471799ea7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


pipeline_configs = sa.table(
    "pipeline_configs",
    sa.column("name", sa.String()),
    sa.column("nodes", sa.JSON()),
    sa.column("enable_living_docs_update", sa.Boolean()),
)


def upgrade() -> None:
    op.execute(
        pipeline_configs.update()
        .where(pipeline_configs.c.name == "zhihu_short")
        .values(
            nodes=["planner", "writer", "editor", "validator", "extractor"],
            enable_living_docs_update=True,
        )
    )


def downgrade() -> None:
    op.execute(
        pipeline_configs.update()
        .where(pipeline_configs.c.name == "zhihu_short")
        .values(
            nodes=["planner", "writer", "editor", "validator"],
            enable_living_docs_update=False,
        )
    )
