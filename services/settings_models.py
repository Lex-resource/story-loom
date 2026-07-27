from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from services.novel_constants import DEFAULT_WATCHDOG_TIMEOUT_SECONDS
from services.settings_constants import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_PROVIDER_ID,
)


class ProviderConfig(BaseModel):
    id: str
    name: str
    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_LLM_MODEL
    embedding_model: str = ""
    cached_models: list[str] = Field(default_factory=list)
    cached_model_details: dict[str, dict] = Field(default_factory=dict)


class SettingsData(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    active_provider_id: str = DEFAULT_PROVIDER_ID
    backup_provider_id: Optional[str] = None
    watchdog_timeout: int = DEFAULT_WATCHDOG_TIMEOUT_SECONDS


class TestProviderRequest(BaseModel):
    provider_id: Optional[str] = None
    base_url: str
    api_key: str
    model: str


TestProviderRequest.__test__ = False
