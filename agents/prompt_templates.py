import logging
import time
from typing import Optional

from agents.constants import PROMPT_CACHE_MAX_ENTRIES, PROMPT_CACHE_TTL_SECONDS


logger = logging.getLogger(__name__)

PromptTemplateValue = tuple[str, str]
PromptTemplateKey = tuple[str, str]


class PromptTemplateCache:
    def __init__(self, ttl_seconds: int, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[PromptTemplateKey, tuple[PromptTemplateValue, float]] = {}

    def get(self, key: PromptTemplateKey, *, now: Optional[float] = None) -> Optional[PromptTemplateValue]:
        now = time.time() if now is None else now
        cached = self._entries.get(key)
        if not cached:
            return None
        value, cached_time = cached
        if now - cached_time < self.ttl_seconds:
            return value
        self._entries.pop(key, None)
        return None

    def get_ignoring_ttl(self, key: PromptTemplateKey) -> Optional[PromptTemplateValue]:
        """版本戳已确认表未变时使用：新鲜度由表戳保证，不再看单条 TTL。"""
        cached = self._entries.get(key)
        return cached[0] if cached else None

    def set(self, key: PromptTemplateKey, value: PromptTemplateValue, *, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self.evict_expired(now=now)
        self._entries[key] = (value, now)
        self.enforce_cap(now=now)

    def invalidate(self, name: Optional[str] = None, category: Optional[str] = None) -> None:
        if name and category:
            self._entries.pop((name, category), None)
        elif name:
            keys_to_remove = [key for key in self._entries if key[0] == name]
            for key in keys_to_remove:
                self._entries.pop(key, None)
        else:
            self._entries.clear()

    def evict_expired(self, *, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        expired = [
            key for key, (_value, cached_time) in self._entries.items()
            if now - cached_time >= self.ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

    def enforce_cap(self, *, now: Optional[float] = None) -> None:
        self.evict_expired(now=now)
        if len(self._entries) <= self.max_entries:
            return
        sorted_keys = sorted(self._entries.items(), key=lambda item: item[1][1])
        overflow = len(self._entries) - self.max_entries
        for key, _value in sorted_keys[:overflow]:
            self._entries.pop(key, None)


_prompt_template_cache = PromptTemplateCache(
    ttl_seconds=PROMPT_CACHE_TTL_SECONDS,
    max_entries=PROMPT_CACHE_MAX_ENTRIES,
)

# prompt_templates 表的当前版本戳；None 表示本进程还没读过库。API 进程改库
# 后，独立 worker 进程靠这条戳感知变化（见 services/config_versions.py）。
# 戳查询失败时保持旧戳不动，缓存退回 TTL 兜底。
_prompt_table_stamp: Optional[tuple[int, str | None]] = None


def invalidate_prompt_cache(name: Optional[str] = None, category: Optional[str] = None) -> None:
    _prompt_template_cache.invalidate(name, category)


async def load_prompt_template(name: str, *, category: str) -> PromptTemplateValue:
    """按 (name, category) 从数据库加载提示词模板，带版本戳 + TTL 双层缓存。

    **不做工作流覆盖解析** —— 那件事在 `agents/base.AgentBase.get_prompt_template`
    里做一次（见 `services/prompt_scope.resolve` 的说明：套两次会在病态映射下翻回去）。
    直接调用本函数会绕过自定义节点的提示词覆盖。

    新鲜度由组合表戳保证：戳一致直接命中缓存（无视单条 TTL），戳变化全清重读。
    戳查询不可用（DB 抖动/迁移未跑）时退回既有 300s TTL 行为 —— 可用性优先于
    新鲜度。
    """
    global _prompt_table_stamp
    cache_key = (name, category)

    from sqlalchemy import select
    from database import async_session
    from models.novel import PromptTemplate

    async with async_session() as session:
        try:
            from services.config_versions import table_version_stamp

            stamp = await table_version_stamp(session, "prompt_templates")
        except Exception:
            logger.warning("prompt_table_stamp_unavailable fallback=ttl", exc_info=True)
            cached = _prompt_template_cache.get(cache_key)
            if cached is not None:
                return cached
        else:
            if stamp != _prompt_table_stamp:
                _prompt_table_stamp = stamp
                _prompt_template_cache.invalidate()
            else:
                cached = _prompt_template_cache.get_ignoring_ttl(cache_key)
                if cached is not None:
                    return cached

        res = await session.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name, PromptTemplate.category == category)
            .order_by(PromptTemplate.is_default.desc(), PromptTemplate.created_at.desc())
            .limit(1)
        )
        tmpl = res.scalar_one_or_none()
        if not tmpl or not tmpl.system_prompt:
            raise ValueError(
                f"数据库中未找到 prompt template: name={name!r}, category={category!r}。"
                f"请确保已在 prompt_templates 表中插入对应记录。"
            )
        value = (tmpl.system_prompt, tmpl.user_prompt_template or "")
        _prompt_template_cache.set(cache_key, value)
        return value
