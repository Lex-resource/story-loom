"""runtime_tunables service 测试。

覆盖:缺行回落默认、非法行忽略、读路径 clamp、写路径校验(未知 key/类型/范围)、
写后快照立即更新、表版本戳变化触发重读。
"""
import asyncio
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.elements import TextClause

from services import runtime_tunables_service as rts


_STAMP_TIME = datetime.datetime(2026, 8, 29, 12, 0, 0)


class _RowsSession:
    """假 session:版本戳走 .one(),行 select 走 .scalars().all()。

    stamp_latest 可变:模拟其他进程 UPDATE 后 MAX(updated_at) 前进。
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.stamp_count = len(self.rows)
        self.stamp_latest = _STAMP_TIME

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        if isinstance(statement, TextClause):
            return SimpleNamespace(
                one=lambda: SimpleNamespace(
                    stamp_count=self.stamp_count, stamp_latest=self.stamp_latest
                )
            )
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self.rows)
        )


class _WriteSession(_RowsSession):
    """额外支持 session.get / add / commit,供 update_values 使用。"""

    def __init__(self, rows):
        super().__init__(rows)
        self.added: dict[str, object] = {}

    async def get(self, model, key):
        for row in self.rows:
            if row.key == key:
                return row
        return None

    def add(self, row):
        self.added[row.key] = row

    async def commit(self):
        for key, row in self.added.items():
            if not any(r.key == key for r in self.rows):
                self.rows.append(row)
        self.added.clear()
        self.stamp_count = len(self.rows)


@pytest.fixture(autouse=True)
def _clean_cache():
    rts.reset_tunables_cache_for_tests()
    yield
    rts.reset_tunables_cache_for_tests()


def _install(monkeypatch, session):
    import database

    monkeypatch.setattr(database, "async_session", lambda: session)


def test_missing_rows_fall_back_to_defaults(monkeypatch):
    _install(monkeypatch, _RowsSession([]))

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 5
    assert asyncio.run(rts.get_value("max_concurrent_jobs")) == 3
    assert asyncio.run(rts.get_value("worker_claim_paused")) is False


def test_row_value_loaded_and_clamped_on_read(monkeypatch):
    # 越界的存量行:读路径 clamp 回范围内,不炸
    _install(
        monkeypatch,
        _RowsSession([SimpleNamespace(key="max_concurrent_jobs", value=999)]),
    )

    assert asyncio.run(rts.get_value("max_concurrent_jobs")) == 32


def test_invalid_row_type_ignored(monkeypatch):
    _install(
        monkeypatch,
        _RowsSession([SimpleNamespace(key="max_concurrent_jobs", value="three")]),
    )

    assert asyncio.run(rts.get_value("max_concurrent_jobs")) == 3


def test_unknown_row_key_ignored(monkeypatch):
    _install(
        monkeypatch,
        _RowsSession([SimpleNamespace(key="removed_param", value=1)]),
    )

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 5


def test_validate_value_rejects_unknown_key_type_and_range():
    with pytest.raises(ValueError):  # 未知 key
        rts.validate_value("no_such_key", 1)
    with pytest.raises(ValueError):  # int 收到字符串
        rts.validate_value("max_concurrent_jobs", "3")
    with pytest.raises(ValueError):  # int 收到布尔值(bool 是 int 子类,先挡)
        rts.validate_value("max_concurrent_jobs", True)
    with pytest.raises(ValueError):  # 超上界
        rts.validate_value("max_concurrent_jobs", 33)
    with pytest.raises(ValueError):  # 低于下界
        rts.validate_value("worker_poll_interval_seconds", 0)
    with pytest.raises(ValueError):  # bool 收到字符串
        rts.validate_value("worker_claim_paused", "yes")
    assert rts.validate_value("worker_claim_paused", True) is True
    assert rts.validate_value("llm_retry_delay_seconds", 10) == 10


def test_update_values_writes_rows_and_refreshes_snapshot(monkeypatch):
    session = _WriteSession([])
    _install(monkeypatch, session)

    values = asyncio.run(rts.update_values({"max_concurrent_jobs": 5}))

    assert values["max_concurrent_jobs"] == 5
    assert asyncio.run(rts.get_value("max_concurrent_jobs")) == 5
    # 落库后表行数变化 → 版本戳变化
    assert session.stamp_count == 1


def test_update_values_rejects_invalid_without_writing(monkeypatch):
    session = _WriteSession([])
    _install(monkeypatch, session)

    with pytest.raises(ValueError):
        asyncio.run(rts.update_values({"max_concurrent_jobs": 999}))

    assert asyncio.run(rts.get_value("max_concurrent_jobs")) == 3
    assert session.added == {}


def test_stamp_change_triggers_reload(monkeypatch):
    session = _RowsSession([SimpleNamespace(key="worker_poll_interval_seconds", value=9)])
    _install(monkeypatch, session)

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 9

    # 另一进程改了表:行值与 MAX(updated_at) 都变 → 下次 get_value 读到新值
    session.rows = [SimpleNamespace(key="worker_poll_interval_seconds", value=12)]
    session.stamp_count = 1
    session.stamp_latest = datetime.datetime(2026, 8, 29, 13, 0, 0)
    rts._last_refresh_monotonic = 0.0  # 手动过期缓存,模拟 TTL 流逝

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 12


def test_stamp_unchanged_skips_reload(monkeypatch):
    """戳未变(如行内容没动)时不重读:快照保持原值。"""
    session = _RowsSession([SimpleNamespace(key="worker_poll_interval_seconds", value=9)])
    _install(monkeypatch, session)

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 9

    session.rows = [SimpleNamespace(key="worker_poll_interval_seconds", value=99)]
    rts._last_refresh_monotonic = 0.0

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 9


def test_deleted_row_falls_back_to_default(monkeypatch):
    """删行洞:reload 时整体回落默认,已删参数的旧值不得永久留在快照里
    (与提示词侧用 COUNT 补删行语义洞同类)。"""
    session = _RowsSession([SimpleNamespace(key="worker_poll_interval_seconds", value=9)])
    _install(monkeypatch, session)

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 9

    # 行被删(仅剩无关行):戳变化触发重读 → 回默认值 5
    session.rows = []
    session.stamp_count = 0
    rts._last_refresh_monotonic = 0.0

    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 5


def test_db_unavailable_falls_back_to_snapshot(monkeypatch):
    class _BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    _install(monkeypatch, _BrokenSession())

    # 首次刷新失败 → 全部回落默认值,不抛
    assert asyncio.run(rts.get_value("worker_poll_interval_seconds")) == 5


def test_vocabulary_groups_cover_all_specs():
    groups = rts.vocabulary()
    listed = {item["key"] for group in groups for item in group["items"]}
    assert listed == set(rts.PARAM_SPECS)
    worker = next(g for g in groups if g["group"] == "worker")
    pause = next(i for i in worker["items"] if i["key"] == "worker_claim_paused")
    assert pause["type"] == "bool" and pause["min"] is None


def test_get_value_sync_rejects_unknown_key():
    with pytest.raises(ValueError):
        rts.get_value_sync("no_such_key")


def test_db_hang_bounded_and_falls_back_to_snapshot(monkeypatch, freeze_tunables):
    """B3:DB 挂死形态(不报错只是永不返回)时,刷新有界放手、读点不死等。"""
    import asyncio as _asyncio

    class _HangingSession:
        async def __aenter__(self):
            await _asyncio.sleep(3600)  # 模拟挂死:不抛错,永不返回

        async def __aexit__(self, *args):
            return False

    _install(monkeypatch, _HangingSession)
    freeze_tunables(worker_poll_interval_seconds=7)  # 预置旧快照值

    async def scenario():
        rts._last_refresh_monotonic = 0.0  # 强制过期,触发刷新
        # 刷新在 5s DB 超时放手 —— 这里给 1s 就应返回(锁内 wait_for 生效)
        await _asyncio.wait_for(rts.ensure_fresh(), timeout=1.0)
        # 读点拿到的是旧快照,不是异常
        assert await rts.get_value("worker_poll_interval_seconds") == 7

    _asyncio.run(scenario())


def test_lock_busy_returns_stale_immediately(monkeypatch, freeze_tunables):
    """等不到刷新锁(别的协程卡在慢刷新里)时立即返回,不排队。"""
    import asyncio as _asyncio

    freeze_tunables(worker_poll_interval_seconds=8)

    async def scenario():
        lock = rts._get_cache_lock()
        await lock.acquire()  # 模拟另一协程持锁刷新中
        try:
            rts._last_refresh_monotonic = 0.0
            await _asyncio.wait_for(rts.ensure_fresh(), timeout=1.0)
            # 期间 get_value 仍可用(旧快照)
            assert await rts.get_value("worker_poll_interval_seconds") == 8
        finally:
            lock.release()

    _asyncio.run(scenario())
