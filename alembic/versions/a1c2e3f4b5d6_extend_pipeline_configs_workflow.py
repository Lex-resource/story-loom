"""Extend pipeline_configs into a workflow record

Revision ID: a1c2e3f4b5d6
Revises: f3a4b5c6d7e8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c2e3f4b5d6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


pipeline_configs = sa.table(
    "pipeline_configs",
    sa.column("name", sa.String()),
    sa.column("surface_strategy", sa.String()),
    sa.column("prompt_category", sa.String()),
    sa.column("policy", sa.JSON()),
    sa.column("quality_dims", sa.JSON()),
)


# 长篇质量维度（研究七维）。
_LONG_DIMS = [
    "plot_progression",
    "character_portrayal",
    "world_consistency",
    "writing_quality",
    "logical_coherence",
    "chapter_continuity",
    "foreshadowing_payoff",
]

# 短篇质量维度（五维手艺 + 两维分节）。
_SHORT_DIMS = [
    "plot_progression",
    "character_portrayal",
    "world_consistency",
    "writing_quality",
    "logical_coherence",
    "hook_strength",
    "emotional_landing",
]

# NovelFormatPolicy 的可配置字段收编到这里。
#
# 刻意**不**写入 ``enable_light_polish``：它今天由 settings.ENABLE_LIGHT_POLISH 决定，
# 在这里硬写 False 会让已在 .env 打开该开关的部署被静默关掉。缺键时
# NovelFormatPolicy.from_policy 回落到代码兜底，也就是继续读环境变量。
_LONG_POLICY = {
    "max_rewrites_override": None,
    "bypass_short_term_memory_window": False,
}
# 短篇三节里每节都是关键节，一稿定生死是缺陷不是设计：给它一次重写机会
# （历史值为 1，即「写完初稿但不允许自动重写」）。
_SHORT_POLICY = {
    "max_rewrites_override": 2,
    "bypass_short_term_memory_window": True,
}


def upgrade() -> None:
    op.add_column("pipeline_configs", sa.Column("stages", sa.JSON(), nullable=True))
    op.add_column("pipeline_configs", sa.Column("policy", sa.JSON(), nullable=True))
    op.add_column("pipeline_configs", sa.Column("surface_strategy", sa.String(length=32), nullable=True))
    op.add_column("pipeline_configs", sa.Column("prompt_category", sa.String(length=50), nullable=True))
    op.add_column("pipeline_configs", sa.Column("quality_dims", sa.JSON(), nullable=True))

    # 存量两行的表面策略 / 提示词 category / 策略 / 维度回填。
    op.execute(
        pipeline_configs.update()
        .where(pipeline_configs.c.name == "long_webnovel")
        .values(
            surface_strategy="frozen_v43",
            prompt_category="long_webnovel",
            policy=_LONG_POLICY,
            quality_dims=_LONG_DIMS,
        )
    )
    op.execute(
        pipeline_configs.update()
        .where(pipeline_configs.c.name == "zhihu_short")
        .values(
            surface_strategy="short_form",
            prompt_category="zhihu_short",
            policy=_SHORT_POLICY,
            quality_dims=_SHORT_DIMS,
        )
    )


def downgrade() -> None:
    op.drop_column("pipeline_configs", "quality_dims")
    op.drop_column("pipeline_configs", "prompt_category")
    op.drop_column("pipeline_configs", "surface_strategy")
    op.drop_column("pipeline_configs", "policy")
    op.drop_column("pipeline_configs", "stages")
