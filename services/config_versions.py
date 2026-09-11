"""配置表版本戳 —— 跨进程缓存新鲜度的统一原语。

独立 worker 进程感知不到 API 进程对配置表的写入；在每个写路径上手工广播
失效必然有漏（新增写路径、直接 SQL、运维改库都会漏）。这里反过来：读侧
每次加载前用一条组合戳查询 ``(COUNT(*), MAX(updated_at))`` 判断表变过没有。

组合戳的关键：纯 ``MAX(updated_at)`` 在"删除最新一行"时不变，``COUNT(*)``
补上这个语义洞。写路径零改动 = 没有可漏的失效点。

表名白名单：戳查询拼的是表名字面量，白名单既防注入也防止对业务大表误用
——组合戳在几十行的配置表上是亚毫秒，在百万行表上不可接受。
"""

from __future__ import annotations

from typing import Tuple

from sqlalchemy import text as _sql_text
from sqlalchemy.ext.asyncio import AsyncSession

# (行数, 最新 updated_at 的 ISO 字符串或 None)
VersionStamp = Tuple[int, str | None]

# 已有 updated_at 列、行数少、被跨进程缓存依赖的配置表。
_VERSIONED_TABLES: set[str] = {"prompt_templates"}


def register_versioned_table(table: str) -> None:
    """把一张表纳入版本戳白名单（如 runtime_tunables 上线时追加）。"""
    _VERSIONED_TABLES.add(table)


async def table_version_stamp(session: AsyncSession, table: str) -> VersionStamp:
    """返回一张配置表的组合版本戳；表变了戳必变，反之不保证（哈希碰撞语义）。"""
    if table not in _VERSIONED_TABLES:
        raise ValueError(
            f"table {table!r} 不在版本戳白名单中（当前白名单: {sorted(_VERSIONED_TABLES)}）"
        )
    row = (
        await session.execute(
            _sql_text(f"SELECT COUNT(*) AS stamp_count, MAX(updated_at) AS stamp_latest FROM {table}")
        )
    ).one()
    latest = row.stamp_latest
    return (int(row.stamp_count), latest.isoformat() if latest is not None else None)
