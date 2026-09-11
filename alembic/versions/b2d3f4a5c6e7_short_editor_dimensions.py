"""Add short-form editor dimensions to zhihu_short prompt rows

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4b5d6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2d3f4a5c6e7"
down_revision: Union[str, Sequence[str], None] = "a1c2e3f4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 短篇 Editor 的响应 schema（EditorShortFormEvaluations）现在要求 hook_strength 与
# emotional_landing。数据库是提示词的运行时权威来源，而 seed_prompts_to_database 只补
# 缺失行、不覆盖既有行 —— 所以文件里改了不等于库里改了，需要这次数据迁移。
#
# 刻意做**定向替换**而不是整段覆盖：用户可能已经在系统配置页改过这些提示词，
# 整段覆盖会吞掉他们的修改。替换点只有评分块和「五维」措辞。
#
# 幂等：已含 hook_strength 的行直接跳过，可重复执行。

_TARGETS = ("editor_review", "editor_force_revise", "editor_destyle")

_OLD_DIM_BLOCK = '"logical_coherence": {"score": 8, "reason": "..."}'
_NEW_DIM_BLOCK = (
    '"logical_coherence": {"score": 8, "reason": "..."},\n'
    '    "hook_strength": {"score": 8, "reason": "本节钩子与追读力"},\n'
    '    "emotional_landing": {"score": 8, "reason": "本节情绪落点是否到位"}'
)

_WORDING = (
    ("五维打分和润色", "七维打分和润色"),
    (
        "需要对五个维度进行 1-10 分打分，并给出具体理由。",
        "需要对七个维度进行 1-10 分打分，并给出具体理由；hook_strength 评本节钩子与追读力，"
        "emotional_landing 评本节情绪落点。",
    ),
    ("并包含五维评分", "并包含七维评分（含 hook_strength、emotional_landing）"),
)

prompt_templates = sa.table(
    "prompt_templates",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("category", sa.String()),
    sa.column("system_prompt", sa.Text()),
)


def _rewrite(system_prompt: str, *, to_seven: bool) -> str:
    text = system_prompt or ""
    if to_seven:
        if "hook_strength" in text:
            return text
        if _OLD_DIM_BLOCK in text:
            text = text.replace(_OLD_DIM_BLOCK, _NEW_DIM_BLOCK, 1)
        for old, new in _WORDING:
            text = text.replace(old, new)
        return text

    # downgrade：回到五维
    if "hook_strength" not in text:
        return text
    text = text.replace(_NEW_DIM_BLOCK, _OLD_DIM_BLOCK, 1)
    for old, new in _WORDING:
        text = text.replace(new, old)
    return text


def _apply(to_seven: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(prompt_templates.c.id, prompt_templates.c.name, prompt_templates.c.system_prompt)
        .where(prompt_templates.c.category == "zhihu_short")
        .where(prompt_templates.c.name.in_(_TARGETS))
    ).fetchall()

    for row in rows:
        updated = _rewrite(row.system_prompt, to_seven=to_seven)
        if updated == (row.system_prompt or ""):
            continue
        bind.execute(
            prompt_templates.update()
            .where(prompt_templates.c.id == row.id)
            .values(system_prompt=updated)
        )


def upgrade() -> None:
    _apply(to_seven=True)


def downgrade() -> None:
    _apply(to_seven=False)
