import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services import access_control
from routers import settings as settings_router


def test_remote_access_is_denied_by_default(monkeypatch):
    monkeypatch.setattr(access_control.settings, "ALLOW_REMOTE_ACCESS", False)
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.8"))
    with pytest.raises(HTTPException) as error:
        access_control.require_local_request(request)
    assert error.value.status_code == 403


def test_settings_redaction_and_blank_key_preservation(monkeypatch):
    stored = {
        "providers": [{"id": "provider-1", "name": "P", "api_key": "secret"}],
        "active_provider_id": "provider-1",
        "backup_provider_id": None,
        "watchdog_timeout": 45,
    }
    saved = {}

    async def fake_load():
        return stored if not saved else saved["value"]

    async def fake_save(value):
        saved["value"] = value

    monkeypatch.setattr(settings_router, "load_settings", fake_load)
    monkeypatch.setattr(settings_router, "_save_settings", fake_save)
    payload = settings_router.SettingsData.model_validate({
        **stored,
        "providers": [{
            "id": "provider-1",
            "name": "P",
            "base_url": "https://example.test/v1",
            "api_key": "",
            "model": "model-1",
        }],
    })

    response = asyncio.run(settings_router.save_settings(payload))

    assert saved["value"]["providers"][0]["api_key"] == "secret"
    assert response["providers"][0]["api_key"] == ""
    assert response["providers"][0]["has_api_key"] is True
