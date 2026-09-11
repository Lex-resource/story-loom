"""runtime_tunables 表:运行参数入库(前端可改、快速生效)。

设计要点:
- PARAM_SPECS 是**单一事实源**,同时喂写路径校验和前端元数据端点,避免两处漂移。
- 不 seed 默认行:缺行 = typed getter 回落 spec 默认(默认值与 config.py 的
  引导值对齐,`.env` 仍是引导配置)。
- 缓存 = TTL(秒级,对齐项目"接受 5 秒级陈旧"的水位)+ 表版本戳
  (services/config_versions.py):戳变了才重读全表,写路径零失效广播。
- 同步读点(task_registry.has_capacity / broadcasting._truncate_for_log /
  AgentBase.__init__ 这类不能 await 的位置)读 get_value_sync 维护的进程内
  快照;worker 的轮询循环每轮都有异步读点,快照新鲜度由它驱动。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from config import settings
from services.config_versions import register_versioned_table, table_version_stamp

logger = logging.getLogger(__name__)

register_versioned_table("runtime_tunables")

_CACHE_TTL_SECONDS = 2.0
# 刷新的两个超时上界:DB"挂死"(不报错只是慢)时,不能让读参数的调用在锁上
# 无限排队 —— 等锁有界(别人在刷就先用旧快照),刷新本身也有界(超时放手)。
# 锁超时取短值:chroma 操作超时本身经 get_value 读取,DB 挂死窗口内单次调用
# 的额外延迟必须远小于那些超时;持锁方最迟 5s 释放,之后 TTL 内不再碰锁。
_REFRESH_LOCK_TIMEOUT_SECONDS = 0.5
_REFRESH_DB_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class TunableSpec:
    key: str
    type: str  # "int" | "float" | "bool"
    default: Any
    min: Any | None
    max: Any | None
    group: str
    description: str
    effective: str  # 生效时机,给前端的说明文案


def _spec(
    key: str,
    type_: str,
    default: Any,
    min_: Any | None,
    max_: Any | None,
    group: str,
    description: str,
    effective: str,
) -> TunableSpec:
    return TunableSpec(
        key=key, type=type_, default=default, min=min_, max=max_,
        group=group, description=description, effective=effective,
    )


PARAM_SPECS: dict[str, TunableSpec] = {
    spec.key: spec
    for spec in [
        # ---- chroma(阶段二吃 #3)----
        _spec("chroma_lock_acquire_timeout_seconds", "int", 60, 10, 600, "chroma",
              "获取 chroma 全局锁的等待上限,超时抛 TimeoutError。", "每次 chroma 调用"),
        _spec("chroma_operation_timeout_seconds", "int", 120, 10, 600, "chroma",
              "单个 chroma 操作的等待上限,超时抛 TimeoutError(操作本身无法取消)。", "每次 chroma 调用"),
        _spec("chroma_zombie_threshold_seconds", "int", 240, 120, 1800, "chroma",
              "操作超过该时长视为僵尸线程,触发 chroma executor 重建(应 > 操作超时)。", "每次 chroma 调用"),
        # ---- embedding ----
        _spec("embedding_max_attempts", "int", 3, 1, 10, "embedding",
              "embedding HTTP 请求的瞬时故障重试次数。", "每次 embedding 请求"),
        _spec("embedding_retry_base_delay_seconds", "float", 1.0, 0.5, 30, "embedding",
              "embedding 重试的基础退避延迟。", "每次重试"),
        _spec("embedding_timeout_seconds", "int", 120, 10, 600, "embedding",
              "embedding HTTP 请求超时。", "每次 embedding 请求"),
        # ---- vector outbox ----
        _spec("vector_outbox_done_retention_seconds", "int", 7 * 24 * 3600, 86400, 2592000, "vector_outbox",
              "已同步完成(DONE)的 outbox 行保留期,超期分批清除。", "下次清理"),
        _spec("vector_outbox_done_cleanup_interval_seconds", "int", 3600, 300, 86400, "vector_outbox",
              "DONE 行清理的执行间隔。", "下一轮循环"),
        _spec("vector_outbox_purge_batch", "int", 500, 50, 5000, "vector_outbox",
              "单批删除的 DONE 行上限(分批短事务,避免长事务阻塞写入)。", "下一批"),
        _spec("vector_outbox_lease_seconds", "int", settings.VECTOR_OUTBOX_LEASE_SECONDS, 60, 3600, "vector_outbox",
              "SYNCING 租约时长,超时的孤儿行回退为 PENDING 重放。", "下次 worker 轮转"),
        # ---- worker ----
        _spec("worker_claim_paused", "bool", False, None, None, "worker",
              "暂停领取新任务(在跑任务继续到检查点)。", "下一轮抢任务"),
        _spec("worker_poll_interval_seconds", "int", settings.WORKER_POLL_INTERVAL, 1, 60, "worker",
              "worker 主循环的轮询间隔。", "下一轮循环"),
        _spec("max_concurrent_jobs", "int", settings.MAX_CONCURRENT_JOBS, 1, 32, "worker",
              "同时运行的生成任务上限。", "下一轮抢任务"),
        _spec("orphan_cleanup_interval_seconds", "int", settings.ORPHAN_CLEANUP_INTERVAL_SECONDS, 30, 3600, "worker",
              "孤儿任务清理的执行间隔。", "下一轮循环"),
        _spec("stale_job_threshold_seconds", "int", settings.STALE_JOB_THRESHOLD_SECONDS, 600, 7200, "worker",
              "RUNNING 任务多久未刷新视为孤儿(须显著大于单章 LLM 总耗时)。", "下次清理"),
        # ---- streaming ----
        _spec("stream_deliver_timeout_seconds", "int", 15, 3, 60, "streaming",
              "单个 WebSocket 客户端的投递超时,超时即踢出。", "下次投递"),
        _spec("log_text_char_limit", "int", 16_000, 2000, 65536, "streaming",
              "广播日志里 prompt/response 正文的截断上限(字符)。", "下次广播"),
        # ---- generation ----
        _spec("post_processing_timeout_seconds", "int", settings.POST_PROCESSING_TIMEOUT_SECONDS, 120, 7200, "generation",
              "单章发布后处理(记忆沉淀/图谱更新)的等待上限。", "下一章"),
        _spec("llm_timeout_seconds", "int", settings.LLM_TIMEOUT, 30, 1800, "generation",
              "单次 LLM 调用超时。", "保存后新建的 agent(下一章)"),
        _spec("llm_max_retries", "int", settings.MAX_LLM_RETRIES, 0, 10, "generation",
              "LLM 调用的最大重试次数。", "下次调用"),
        _spec("llm_retry_delay_seconds", "int", settings.RETRY_DELAY, 1, 60, "generation",
              "LLM 重试的基础退避延迟。", "下次重试"),
    ]
}


# 进程内快照:同步读点的数据源,由异步读点的 TTL/戳校验驱动刷新。
_snapshot: dict[str, Any] = {spec.key: spec.default for spec in PARAM_SPECS.values()}
_last_refresh_monotonic = 0.0
_last_stamp: tuple[int, str | None] | None = None
_cache_lock: asyncio.Lock | None = None


def _get_cache_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def reset_tunables_cache_for_tests() -> None:
    global _last_refresh_monotonic, _last_stamp, _cache_lock
    for spec in PARAM_SPECS.values():
        _snapshot[spec.key] = spec.default
    _last_refresh_monotonic = 0.0
    _last_stamp = None
    _cache_lock = None


def _clamp(spec: TunableSpec, value: Any) -> Any:
    if spec.type in ("int", "float") and spec.min is not None and value < spec.min:
        return spec.min
    if spec.type in ("int", "float") and spec.max is not None and value > spec.max:
        return spec.max
    return value


def validate_value(key: str, value: Any) -> Any:
    """写路径校验:未知 key/类型/范围都抛 ValueError(中文 message,由 router 转 400)。"""
    spec = PARAM_SPECS.get(key)
    if spec is None:
        raise ValueError(f"未知参数: {key}")
    if spec.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"参数 {key} 需要布尔值,收到 {value!r}")
        return value
    if isinstance(value, bool):  # bool 是 int 子类,先挡掉
        raise ValueError(f"参数 {key} 需要{('整数' if spec.type == 'int' else '数字')},收到布尔值")
    if spec.type == "int":
        if not isinstance(value, int):
            raise ValueError(f"参数 {key} 需要整数,收到 {value!r}")
    else:
        if not isinstance(value, (int, float)):
            raise ValueError(f"参数 {key} 需要数字,收到 {value!r}")
        value = float(value)
    if spec.min is not None and value < spec.min:
        raise ValueError(f"参数 {key} 不能小于 {spec.min},收到 {value}")
    if spec.max is not None and value > spec.max:
        raise ValueError(f"参数 {key} 不能大于 {spec.max},收到 {value}")
    return value


def get_value_sync(key: str) -> Any:
    """同步读点专用:返回进程内快照值(可能有秒级陈旧)。未知 key 直接抛。"""
    spec = PARAM_SPECS.get(key)
    if spec is None:
        raise ValueError(f"未知参数: {key}")
    return _snapshot[key]


async def get_value(key: str) -> Any:
    """异步读点:先做 TTL/戳校验刷新快照,再取值。DB 不可用时回落旧快照。"""
    await ensure_fresh()
    return get_value_sync(key)


async def ensure_fresh() -> None:
    """TTL 过期后用表版本戳判断是否重读全表;失败/超时保持旧快照(可用性优先)。

    两个超时保证 DB 挂死形态下读参数的调用不会在锁上无限排队:
    - 锁获取有界:另一个刷新正卡在慢查询时,等不到锁就直接用旧快照;
    - 刷新本身有界:wait_for 超时后锁随 async with 退出释放,TTL 计时重启,
      不会形成紧循环重试。
    """
    global _last_refresh_monotonic, _last_stamp
    now = time.monotonic()
    if now - _last_refresh_monotonic < _CACHE_TTL_SECONDS:
        return
    try:
        await asyncio.wait_for(
            _get_cache_lock().acquire(), timeout=_REFRESH_LOCK_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.debug("runtime_tunables_refresh_lock_busy fallback=stale_snapshot")
        return
    try:
        now = time.monotonic()
        if now - _last_refresh_monotonic < _CACHE_TTL_SECONDS:
            return
        try:
            from database import async_session

            async def _refresh_once():
                global _last_stamp
                async with async_session() as session:
                    stamp = await table_version_stamp(session, "runtime_tunables")
                    if stamp != _last_stamp:
                        await _load_rows(session)
                        _last_stamp = stamp

            await asyncio.wait_for(_refresh_once(), timeout=_REFRESH_DB_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("runtime_tunables_refresh_timeout fallback=stale_snapshot")
        except Exception:
            logger.warning("runtime_tunables_refresh_failed fallback=stale_snapshot", exc_info=True)
        finally:
            _last_refresh_monotonic = time.monotonic()
    finally:
        _get_cache_lock().release()


def _coerce_row_value(spec: TunableSpec, value: Any) -> tuple[bool, Any]:
    """读路径的宽容转换:类型对就 clamp,类型不对返回 (False, value) 让调用方回落默认。

    与写路径的 validate_value(越界拒绝)不同:表里的行都是历史写入,类型
    不认识的行忽略即可,能认的就 clamp 回范围内继续用。
    """
    if spec.type == "bool":
        return (isinstance(value, bool), value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return (False, value)
    return (True, _clamp(spec, value))


async def _load_rows(session) -> None:
    from sqlalchemy import select

    from models.operations import RuntimeTunable

    rows = (await session.execute(select(RuntimeTunable))).scalars().all()
    # 先整体回落默认再覆盖表内行:删行(手删 SQL/运维清理)也要回到默认值 ——
    # 这与提示词侧用 COUNT(*) 补"删最新行"语义洞是同一类问题,快照只覆盖
    # 表内存在的 key 会把已删参数的旧值永久留在内存里。
    # 重建完整 dict 后一次性换引用:同步读点(get_value_sync 可被工作线程调用)
    # 读到的要么是旧快照要么是新快照,不会看到逐键写入的中间态。
    fresh: dict[str, Any] = {spec.key: spec.default for spec in PARAM_SPECS.values()}
    for row in rows:
        spec = PARAM_SPECS.get(row.key)
        if spec is None:
            continue  # 表里残留的已下线参数:忽略
        ok, value = _coerce_row_value(spec, row.value)
        if not ok:
            logger.warning("runtime_tunables_invalid_row key=%s value=%r", row.key, row.value)
            continue
        fresh[spec.key] = value
    global _snapshot
    _snapshot = fresh


async def update_values(values: dict[str, Any]) -> dict[str, Any]:
    """全量校验后原子写入;成功后失效缓存,让本进程下一次读立即刷新。

    返回写入后的实际值(规范化 + clamp)。校验失败抛 ValueError,不落任何行。
    """
    global _snapshot
    normalized = {key: validate_value(key, value) for key, value in values.items()}
    if not normalized:
        return dict(_snapshot)

    from database import async_session
    from models.operations import RuntimeTunable

    async with async_session() as session:
        for key, value in normalized.items():
            row = await session.get(RuntimeTunable, key)
            if row is None:
                row = RuntimeTunable(key=key, value=value)
                session.add(row)
            else:
                row.value = value
        await session.commit()

    _invalidate()
    # 同样整体换引用,避免跨线程读点看到逐键写入的中间态
    merged = dict(_snapshot)
    merged.update(normalized)
    _snapshot = merged
    return {key: merged[key] for key in normalized}


def _invalidate() -> None:
    global _last_refresh_monotonic, _last_stamp
    _last_refresh_monotonic = 0.0
    _last_stamp = None


def vocabulary() -> list[dict[str, Any]]:
    """前端元数据:按 group 分组下发,前端不写死任何参数。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in PARAM_SPECS.values():
        groups.setdefault(spec.group, []).append(
            {
                "key": spec.key,
                "type": spec.type,
                "default": spec.default,
                "min": spec.min,
                "max": spec.max,
                "description": spec.description,
                "effective": spec.effective,
            }
        )
    return [{"group": group, "items": items} for group, items in groups.items()]


def current_values() -> dict[str, Any]:
    return dict(_snapshot)
