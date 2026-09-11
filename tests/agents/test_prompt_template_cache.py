"""提示词模板跨进程热生效测试。

核心场景模拟 worker 眼中的世界:缓存已填充后,另一个进程(API)绕过
invalidate_prompt_cache 直接改库 —— 本进程的下一个 load 必须读到新文本。
DELETE 走 ValueError,INSERT 新键可读;戳查询失败退回 TTL 兜底。
"""
import asyncio
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.elements import TextClause

from agents import prompt_templates
from agents.prompt_templates import PromptTemplateCache, load_prompt_template


class _FakeResult:
    """同时满足两条读路径:版本戳走 .one(),ORM select 走 .scalar_one_or_none()。"""

    def __init__(self, tmpl, stamp):
        self._tmpl = tmpl
        self._stamp = stamp

    def one(self):
        return self._stamp

    def scalar_one_or_none(self):
        return self._tmpl


class _FakeSession:
    def __init__(self):
        self.tmpl = SimpleNamespace(
            system_prompt="旧系统提示词",
            user_prompt_template="旧用户提示词",
            is_default=1,
            created_at=datetime.datetime(2026, 1, 1),
        )
        self.stamp = SimpleNamespace(stamp_count=1, stamp_latest=datetime.datetime(2026, 1, 1, 12, 0, 0))
        # 置 True 时戳查询抛异常(模拟 DB 抖动/迁移未跑)
        self.stamp_broken = False

    async def execute(self, statement):
        # 只让版本戳查询(text() 语句)失败,ORM select 照常 —— 模拟"戳不可用
        # 但库还能查"的降级场景。
        if self.stamp_broken and isinstance(statement, TextClause):
            raise RuntimeError("stamp query unavailable")
        return _FakeResult(self.tmpl, self.stamp)


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(prompt_templates, "_prompt_template_cache", PromptTemplateCache(ttl_seconds=300, max_entries=256))
    monkeypatch.setattr(prompt_templates, "_prompt_table_stamp", None)
    yield


def _install(monkeypatch, session):
    import database

    monkeypatch.setattr(database, "async_session", lambda: _FakeSessionFactory(session))


class _FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_load_reads_db_and_caches(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session)

    value = asyncio.run(load_prompt_template("writer", category="long_webnovel"))
    assert value == ("旧系统提示词", "旧用户提示词")

    # 表未变时,即使模板对象被换成新文本也不重读(戳一致 → 命中缓存)
    session.tmpl.system_prompt = "这段不该被读到"
    value = asyncio.run(load_prompt_template("writer", category="long_webnovel"))
    assert value == ("旧系统提示词", "旧用户提示词")


def test_other_process_update_is_seen_without_invalidate(monkeypatch):
    """核心场景:API 进程改库(worker 进程内没有 invalidate)→ 下次 load 读到新文本。"""
    session = _FakeSession()
    _install(monkeypatch, session)

    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "旧系统提示词",
        "旧用户提示词",
    )

    # 模拟 API 进程的 UPDATE:文本变 + updated_at 前进
    session.tmpl.system_prompt = "新系统提示词"
    session.stamp.stamp_latest = datetime.datetime(2026, 8, 29, 15, 0, 0)

    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "新系统提示词",
        "旧用户提示词",
    )


def test_other_process_delete_raises_value_error(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session)

    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "旧系统提示词",
        "旧用户提示词",
    )

    # 模拟 API 进程的 DELETE:行没了(COUNT 归零是关键 —— 纯 MAX 感知不到删最新行)
    session.tmpl = None
    session.stamp.stamp_count = 0
    session.stamp.stamp_latest = datetime.datetime(2026, 1, 1, 12, 0, 0)

    with pytest.raises(ValueError):
        asyncio.run(load_prompt_template("writer", category="long_webnovel"))


def test_other_process_insert_new_key_is_readable(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session)
    session.tmpl = None
    session.stamp.stamp_count = 0

    with pytest.raises(ValueError):
        asyncio.run(load_prompt_template("writer_terse", category="long_webnovel"))

    # INSERT:行数 +1,新键立即可读(无需等 TTL 过期)
    session.tmpl = SimpleNamespace(
        system_prompt="精简版系统提示词",
        user_prompt_template="",
        is_default=1,
        created_at=datetime.datetime(2026, 8, 29),
    )
    session.stamp.stamp_count = 1
    session.stamp.stamp_latest = datetime.datetime(2026, 8, 29, 16, 0, 0)

    assert asyncio.run(load_prompt_template("writer_terse", category="long_webnovel")) == (
        "精简版系统提示词",
        "",
    )


def test_stamp_failure_falls_back_to_ttl_cache(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session)

    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "旧系统提示词",
        "旧用户提示词",
    )

    # 戳查询坏了:退回 TTL 兜底 —— 缓存未过期时沿用旧值,不炸
    session.stamp_broken = True
    session.tmpl.system_prompt = "这段不该被读到"
    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "旧系统提示词",
        "旧用户提示词",
    )


def test_stamp_failure_with_empty_cache_hits_db(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session)
    session.stamp_broken = True

    # 无缓存可用 → 仍要能从库加载(可用性优先)
    assert asyncio.run(load_prompt_template("writer", category="long_webnovel")) == (
        "旧系统提示词",
        "旧用户提示词",
    )


def test_ttl_regression_with_injected_now(monkeypatch):
    """戳兜底路径的既有 TTL 行为回归:过期条目不再返回。"""
    cache = PromptTemplateCache(ttl_seconds=300, max_entries=256)
    cache.set(("writer", "cat"), ("s", "u"), now=1000.0)
    assert cache.get(("writer", "cat"), now=1200.0) == ("s", "u")
    assert cache.get(("writer", "cat"), now=1400.0) is None
