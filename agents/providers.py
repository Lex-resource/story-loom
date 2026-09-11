from dataclasses import dataclass
from typing import Optional

from config import settings


@dataclass(frozen=True)
class ProviderSelection:
    base_url: str
    api_key: str
    model: str
    provider_name: Optional[str] = None
    embedding_model: Optional[str] = None


def resolve_active_provider(app_settings: dict, model_override: Optional[str] = None) -> ProviderSelection:
    providers = app_settings.get("providers", [])
    active_id = app_settings.get("active_provider_id", "default")
    active_provider = next((provider for provider in providers if provider.get("id") == active_id), None)
    if not active_provider and providers:
        active_provider = providers[0]
    base_url = active_provider.get("base_url", settings.LLM_BASE_URL) if active_provider else settings.LLM_BASE_URL
    api_key = active_provider.get("api_key", settings.LLM_API_KEY) if active_provider else settings.LLM_API_KEY
    model = active_provider.get("model", settings.LLM_MODEL) if active_provider else settings.LLM_MODEL
    if model_override:
        model = model_override
    return ProviderSelection(
        base_url=base_url,
        api_key=api_key,
        model=model,
        provider_name=active_provider.get("name") if active_provider else None,
        embedding_model=(
            active_provider.get("embedding_model")
            if active_provider
            else None
        ) or settings.EMBEDDING_MODEL or None,
    )


def resolve_backup_provider(
    app_settings: dict,
    current_base_url: str,
    current_api_key: str,
    current_model: str,
) -> tuple[bool, ProviderSelection]:
    providers = app_settings.get("providers", [])
    active_id = app_settings.get("active_provider_id", "default")
    backup_id = app_settings.get("backup_provider_id")
    backup_provider = None
    if backup_id and backup_id != active_id:
        backup_provider = next((provider for provider in providers if provider.get("id") == backup_id), None)
    # A backup provider is opt-in. Never silently route requests to an
    # arbitrary configured provider that the user did not designate.
    if not backup_provider:
        return False, ProviderSelection(current_base_url, current_api_key, current_model)
    return True, ProviderSelection(
        base_url=backup_provider.get("base_url", current_base_url),
        api_key=backup_provider.get("api_key", current_api_key),
        model=backup_provider.get("model", current_model),
        provider_name=backup_provider.get("name"),
        embedding_model=backup_provider.get("embedding_model") or None,
    )
