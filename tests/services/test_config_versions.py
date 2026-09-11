"""config_versions 组合版本戳测试。

戳的语义:UPDATE/INSERT/DELETE 任一都会改变 (COUNT(*), MAX(updated_at)) 组合
——纯 MAX 在"删除最新一行"时不变,COUNT 补上这个洞。表名白名单拒绝越权表。
"""
import asyncio
import datetime
from types import SimpleNamespace

import pytest

from services import config_versions
from services.config_versions import table_version_stamp


class _Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _Session:
    """假 session:execute 返回可变的戳行,模拟表内容的变化。"""

    def __init__(self):
        self.row = SimpleNamespace(stamp_count=2, stamp_latest=datetime.datetime(2026, 8, 29, 12, 0, 0))

    async def execute(self, statement):
        return _Result(self.row)


def test_stamp_reflects_count_and_latest():
    stamp = asyncio.run(table_version_stamp(_Session(), "prompt_templates"))
    assert stamp == (2, "2026-08-29T12:00:00")


def test_stamp_changes_on_update_insert_and_delete():
    session = _Session()
    before = asyncio.run(table_version_stamp(session, "prompt_templates"))

    # UPDATE:行数不变,MAX(updated_at) 前进
    session.row.stamp_latest = datetime.datetime(2026, 8, 29, 13, 0, 0)
    assert asyncio.run(table_version_stamp(session, "prompt_templates")) != before

    # INSERT:行数与 MAX 都变
    session.row.stamp_count = 3
    assert asyncio.run(table_version_stamp(session, "prompt_templates"))[0] == 3

    # DELETE 最新一行:行数变(COUNT 补上纯 MAX 的语义洞)
    session.row.stamp_count = 2
    session.row.stamp_latest = datetime.datetime(2026, 8, 29, 12, 0, 0)
    after_delete = asyncio.run(table_version_stamp(session, "prompt_templates"))
    assert after_delete == before
    assert after_delete != (3, "2026-08-29T13:00:00")


def test_stamp_handles_empty_table():
    session = _Session()
    session.row = SimpleNamespace(stamp_count=0, stamp_latest=None)
    assert asyncio.run(table_version_stamp(session, "prompt_templates")) == (0, None)


def test_unregistered_table_rejected():
    with pytest.raises(ValueError):
        asyncio.run(table_version_stamp(_Session(), "chapters"))


def test_register_versioned_table_extends_whitelist():
    # 用一次性临时表名,不要动 runtime_tunables —— 它已在服务导入时注册,
    # 在这里 discard 会污染同进程的其他测试。
    config_versions.register_versioned_table("tmp_whitelist_probe")
    try:
        stamp = asyncio.run(table_version_stamp(_Session(), "tmp_whitelist_probe"))
        assert stamp == (2, "2026-08-29T12:00:00")
        with pytest.raises(ValueError):
            asyncio.run(table_version_stamp(_Session(), "still_not_registered"))
    finally:
        config_versions._VERSIONED_TABLES.discard("tmp_whitelist_probe")
