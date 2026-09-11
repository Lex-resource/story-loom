"""Workflow graph column + reusable workflow node library

Revision ID: d4a5b6c7e8f9
Revises: c3e4a5b6d7f8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4a5b6c7e8f9"
down_revision: Union[str, Sequence[str], None] = "c3e4a5b6d7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 内置节点库。每个角色一个内置节点，``prompt_name`` 留空表示用该角色写死的内置提示词。
#
# id 用 "<agent>.<role>" 的形式而不是裸角色名，因为界面上要按 agent 归组，而
# 自定义节点会形如 "editor.review.savage" —— 前缀一致才看得出它替换的是哪一步。
#
# ``context_refresh`` 与 ``publish`` 是系统角色（没有 agent、没有提示词），前缀用
# "system"。它们不可删也不可换提示词，但必须在库里有行，否则图里引用它们的步骤会
# 因为查不到节点而被校验器判为非法。
_NODES = [
    # (id, name_zh, role, description)
    ("planner.outline", "大纲策划", "outline",
     "生成或复用本章分章大纲。复用时不消耗 planner 的 token。"),
    ("system.context_refresh", "上下文刷新", "context_refresh",
     "系统步骤：重写循环顶部重新加载记忆与上下文，并判断本轮是否需要重写初稿。"),
    ("writer.draft", "初稿撰写", "draft",
     "写本章正文。重写时会带上一版的校验错误作为修改指令。"),
    ("validator.pre_editor", "编辑前置校验", "pre_editor",
     "编辑之前先校验一次，把硬伤作为审阅输入交给编辑。"),
    ("editor.review", "编辑审阅", "review",
     "按质量维度打分，可判定打回重写。"),
    ("editor.force_revise", "强制修正", "force_revise",
     "重写预算耗尽后由编辑直接修正。只能从重写边到达。"),
    ("validator.post_edit", "编辑后校验", "post_edit",
     "校验编辑产出的润色稿，可要求再走一轮。"),
    ("editor.style_repair", "去 AI 腔", "style_repair",
     "检测到套话密度或句式单一时做纯文风修复，不改剧情。有确定性门控，常常不实际调用。"),
    ("validator.final", "终审与字数", "final",
     "发布前的最终校验。已有完整校验结论时复用，不重复烧一次。"),
    ("system.publish", "落定校验结论", "publish",
     "系统步骤：把校验结论写入章节。强制保存的章节在这里暂停等人工复核。"),
    ("extractor.postprocess", "沉淀记忆并发布", "postprocess",
     "提取设定、写入分层记忆并发布章节。"),
]


def upgrade() -> None:
    op.add_column("pipeline_configs", sa.Column("graph", sa.JSON(), nullable=True))
    op.add_column(
        "pipeline_configs",
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("pipeline_configs", sa.Column("description", sa.Text(), nullable=True))

    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name_zh", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("prompt_name", sa.String(length=100), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    # 刻意不给 role 建索引：这张表是节点库，规模是十几行到几十行，索引只会让
    # `command.check` 与 ORM 元数据对不上而毫无收益。

    nodes = sa.table(
        "workflow_nodes",
        sa.column("id", sa.String()),
        sa.column("name_zh", sa.String()),
        sa.column("role", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("builtin", sa.Boolean()),
    )
    statement = postgresql.insert(nodes).values(
        [
            {
                "id": node_id,
                "name_zh": name_zh,
                "role": role,
                "description": description,
                "builtin": True,
            }
            for node_id, name_zh, role, description in _NODES
        ]
    )
    # 只补缺失行，不覆盖任何人改过的中文名或说明。
    op.execute(statement.on_conflict_do_nothing(index_elements=["id"]))

    # 两行生产工作流标为内置：删掉任何一个都会让存量项目查不到流程配置。
    # ``graph`` 刻意留 NULL —— 代码里的 default_graph() 是默认拓扑的权威，
    # golden trace 钉的也是它。写死一份 JSON 进库反而会让两者可能漂移。
    pipeline_configs = sa.table(
        "pipeline_configs",
        sa.column("name", sa.String()),
        sa.column("builtin", sa.Boolean()),
    )
    op.execute(
        pipeline_configs.update()
        .where(pipeline_configs.c.name.in_(["long_webnovel", "zhihu_short"]))
        .values(builtin=True)
    )

    # server_default 只是为了给存量行回填，之后交给 ORM 默认值。
    op.alter_column("pipeline_configs", "builtin", server_default=None)
    op.alter_column("workflow_nodes", "builtin", server_default=None)


def downgrade() -> None:
    op.drop_table("workflow_nodes")
    op.drop_column("pipeline_configs", "description")
    op.drop_column("pipeline_configs", "builtin")
    op.drop_column("pipeline_configs", "graph")
