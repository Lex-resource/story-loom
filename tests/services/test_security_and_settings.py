import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from services import access_control
from services import provider_testing
from routers import settings as settings_router
from main import app


def test_remote_access_is_denied_by_default(monkeypatch):
    monkeypatch.setattr(access_control.settings, "ALLOW_REMOTE_ACCESS", False)
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.8"))
    with pytest.raises(HTTPException) as error:
        access_control.require_local_request(request)
    assert error.value.status_code == 403


def test_remote_access_requires_configured_token(monkeypatch):
    monkeypatch.setattr(access_control.settings, "ALLOW_REMOTE_ACCESS", True)
    monkeypatch.setattr(access_control.settings, "REMOTE_ACCESS_TOKEN", "remote-secret")
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.8"),
        headers={},
    )
    with pytest.raises(HTTPException) as error:
        access_control.require_local_request(request)
    assert error.value.status_code == 403


def test_remote_access_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(access_control.settings, "ALLOW_REMOTE_ACCESS", True)
    monkeypatch.setattr(access_control.settings, "REMOTE_ACCESS_TOKEN", "remote-secret")
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.8"),
        headers={"Authorization": "Bearer remote-secret"},
    )
    access_control.require_local_request(request)


def test_provider_target_rejects_private_and_credential_bearing_urls(monkeypatch):
    monkeypatch.setattr(
        provider_testing.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError):
        provider_testing.validate_provider_base_url("http://127.0.0.1:8000")
    with pytest.raises(ValueError):
        provider_testing.validate_provider_base_url("https://user:pass@example.test")


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

    monkeypatch.setattr(
        provider_testing.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

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


class _RemoteClientScope:
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = ("203.0.113.8", 12345)
        await self.asgi_app(scope, receive, send)


@pytest.mark.asyncio
async def test_remote_http_guard_returns_json_403(monkeypatch):
    monkeypatch.setattr(access_control.settings, "ALLOW_REMOTE_ACCESS", False)
    transport = httpx.ASGITransport(app=_RemoteClientScope(app))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/writing/projects")

    assert response.status_code == 403
    assert response.json()["detail"] == "Remote access is disabled"
