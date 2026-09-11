"""Seed system_nodes and system_doc_types dictionaries

Revision ID: c3e4a5b6d7f8
Revises: b2d3f4a5c6e7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3e4a5b6d7f8"
down_revision: Union[str, Sequence[str], None] = "b2d3f4a5c6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 这两张字典表由 e71ac504ace1 建出，但**仓库里从来没有任何种子代码**：唯一的读取点是
# system_configs_service.list_available_nodes 的 select。已有环境是手工填过数据才正常，
# 全新安装则 GET /available-nodes 返回 []，系统配置页的节点勾选框整块是空的。
#
# 用 ON CONFLICT DO NOTHING：只补缺失行，不覆盖任何人改过的中文名。
_NODES = [
    ("planner", "大纲策划 (planner)"),
    ("writer", "初稿撰写 (writer)"),
    ("editor", "编辑精修 (editor)"),
    ("validator", "天道校验 (validator)"),
    ("extractor", "设定提取 (extractor)"),
]

_DOC_TYPES = [
    ("world_state", "世界设定 (world_state)"),
    ("character_state", "角色设定 (character_state)"),
    ("foreshadowing", "伏笔记录 (foreshadowing)"),
    ("plot_threads", "剧情主线 (plot_threads)"),
]


def _table(name: str):
    return sa.table(name, sa.column("id", sa.String()), sa.column("name_zh", sa.String()))


def upgrade() -> None:
    for table_name, rows in (("system_nodes", _NODES), ("system_doc_types", _DOC_TYPES)):
        table = _table(table_name)
        statement = postgresql.insert(table).values(
            [{"id": key, "name_zh": label} for key, label in rows]
        )
        op.execute(statement.on_conflict_do_nothing(index_elements=["id"]))


def downgrade() -> None:
    # 只删本迁移登记的键；手工添加的其他行保持不动。
    for table_name, rows in (("system_nodes", _NODES), ("system_doc_types", _DOC_TYPES)):
        table = _table(table_name)
        op.execute(table.delete().where(table.c.id.in_([key for key, _ in rows])))
