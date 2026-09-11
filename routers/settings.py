import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.settings_constants import DEFAULT_LLM_BASE_URL
from services.provider_testing import (
    test_provider_connection_logic,
    list_models_by_provider_logic,
    validate_provider_base_url,
)
from services.settings_models import SettingsData, TestProviderRequest
from services.settings_store import get_active_provider, load_settings, save_settings as _save_settings

router = APIRouter()


class ModelsByProviderRequest(BaseModel):
    provider_id: str | None = None
    base_url: str
    api_key: str = ""


def _redact_settings(data: dict) -> dict:
    redacted = {**data, "providers": []}
    for provider in data.get("providers", []):
        item = dict(provider)
        item["has_api_key"] = bool(item.get("api_key"))
        item["api_key"] = ""
        redacted["providers"].append(item)
    return redacted


async def _resolve_provider_secret(provider_id: str | None, api_key: str) -> str:
    if api_key:
        return api_key
    settings_data = await load_settings()
    for provider in settings_data.get("providers", []):
        if provider.get("id") == provider_id:
            return provider.get("api_key", "")
    return ""


@router.get("/settings")
async def get_settings():
    return _redact_settings(await load_settings())

@router.post("/settings")
async def save_settings(data: SettingsData):
    incoming = data.model_dump()
    for provider in incoming.get("providers", []):
        try:
            provider["base_url"] = await asyncio.to_thread(
                validate_provider_base_url,
                provider.get("base_url", ""),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Provider '{provider.get('id', '')}' 的 API 地址无效：{exc}",
            ) from exc
    existing = await load_settings()
    existing_keys = {provider.get("id"): provider.get("api_key", "") for provider in existing.get("providers", [])}
    for provider in incoming.get("providers", []):
        if not provider.get("api_key"):
            provider["api_key"] = existing_keys.get(provider.get("id"), "")
    await _save_settings(incoming)
    return _redact_settings(await load_settings())

@router.post("/settings/test-provider")
async def test_provider_connection(req: TestProviderRequest):
    req.api_key = await _resolve_provider_secret(req.provider_id, req.api_key)
    if not req.api_key:
        raise HTTPException(status_code=422, detail="API key is required")
    return await test_provider_connection_logic(req)

@router.post("/settings/models-by-provider")
async def list_models_by_provider(req: ModelsByProviderRequest):
    api_key = await _resolve_provider_secret(req.provider_id, req.api_key)
    if not api_key:
        raise HTTPException(status_code=422, detail="API key is required")
    return await list_models_by_provider_logic(req.base_url, api_key)

@router.post("/settings/test")
async def test_connection():
    active_provider = await get_active_provider()

    if not active_provider:
        return {"ok": False, "error": "没有配置提供商"}

    req = TestProviderRequest(
        base_url=active_provider.get("base_url", ""),
        api_key=active_provider.get("api_key", ""),
        model=active_provider.get("model", "")
    )
    return await test_provider_connection_logic(req)

@router.get("/settings/models")
async def list_available_models():
    active_provider = await get_active_provider()

    if not active_provider:
        return {"ok": False, "error": "没有配置提供商", "models": []}

    return await list_models_by_provider_logic(
        base_url=active_provider.get("base_url", DEFAULT_LLM_BASE_URL),
        api_key=active_provider.get("api_key", "")
    )
