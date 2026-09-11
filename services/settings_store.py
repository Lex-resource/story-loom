from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from models.novel import SystemSettings
from services.settings_constants import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_PROVIDER_ID,
    DEFAULT_PROVIDER_NAME,
)


import logging

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(settings.SETTINGS_FILE)
GLOBAL_SETTINGS_ID = "global_config"
SETTINGS_CACHE_TTL_SECONDS: float = 5.0

_settings_cache: tuple[dict, float] | None = None
_settings_cache_lock: asyncio.Lock | None = None


def get_settings_cache_lock() -> asyncio.Lock:
    global _settings_cache_lock
    if _settings_cache_lock is None:
        _settings_cache_lock = asyncio.Lock()
    return _settings_cache_lock


def default_settings() -> dict:
    return {
        "providers": [{
            "id": DEFAULT_PROVIDER_ID,
            "name": DEFAULT_PROVIDER_NAME,
            "base_url": DEFAULT_LLM_BASE_URL,
            "api_key": "",
            "model": DEFAULT_LLM_MODEL,
            "embedding_model": "",
        }],
        "active_provider_id": DEFAULT_PROVIDER_ID,
    }


async def query_settings(session: AsyncSession) -> dict:
    result = await session.execute(select(SystemSettings).where(SystemSettings.id == GLOBAL_SETTINGS_ID))
    record = result.scalar_one_or_none()
    if record:
        return record.value

    data = load_legacy_settings_file()
    if "providers" not in data or not data["providers"]:
        data = default_settings()

    session.add(SystemSettings(id=GLOBAL_SETTINGS_ID, value=data))
    await session.commit()
    return data


def load_legacy_settings_file() -> dict:
    """Read the one-time legacy file fallback; SystemSettings is authoritative."""
    if not SETTINGS_FILE.exists():
        return default_settings()
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_settings()


async def load_settings(db: Optional[AsyncSession] = None) -> dict:
    global _settings_cache
    if _settings_cache is not None and not db:
        cached_data, cached_ts = _settings_cache
        if time.time() - cached_ts < SETTINGS_CACHE_TTL_SECONDS:
            return cached_data

    if db:
        return await query_settings(db)

    lock = get_settings_cache_lock()
    async with lock:
        if _settings_cache is not None:
            cached_data, cached_ts = _settings_cache
            if time.time() - cached_ts < SETTINGS_CACHE_TTL_SECONDS:
                return cached_data

        async with async_session() as session:
            data = await query_settings(session)
            _settings_cache = (data, time.time())
            return data


async def save_settings(data: dict, db: Optional[AsyncSession] = None) -> None:
    global _settings_cache

    async def save_to_session(session: AsyncSession) -> None:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == GLOBAL_SETTINGS_ID))
        record = result.scalar_one_or_none()
        if record:
            record.value = data
        else:
            session.add(SystemSettings(id=GLOBAL_SETTINGS_ID, value=data))
        await session.commit()

    if db:
        await save_to_session(db)
    else:
        async with async_session() as session:
            await save_to_session(session)

    lock = get_settings_cache_lock()
    async with lock:
        _settings_cache = None

    remove_legacy_settings_file()


def remove_legacy_settings_file() -> None:
    if not SETTINGS_FILE.exists():
        return
    try:
        SETTINGS_FILE.unlink()
    except Exception as exc:
        logger.warning(f"[Settings WARN] Failed to remove stale settings file {SETTINGS_FILE}: {exc}")


async def get_active_provider() -> Optional[dict]:
    settings_data = await load_settings()
    providers = settings_data.get("providers", [])
    active_id = settings_data.get("active_provider_id", DEFAULT_PROVIDER_ID)
    for provider in providers:
        if provider.get("id") == active_id:
            return provider
    if providers:
        return providers[0]
    return None
