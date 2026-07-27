import time
from typing import Optional

from agents.constants import PROMPT_CACHE_MAX_ENTRIES, PROMPT_CACHE_TTL_SECONDS


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


def invalidate_prompt_cache(name: Optional[str] = None, category: Optional[str] = None) -> None:
    _prompt_template_cache.invalidate(name, category)


async def load_prompt_template(name: str, *, category: str) -> PromptTemplateValue:
    cache_key = (name, category)
    cached = _prompt_template_cache.get(cache_key)
    if cached is not None:
        return cached

    from sqlalchemy import select
    from database import async_session
    from models.novel import PromptTemplate

    async with async_session() as session:
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
