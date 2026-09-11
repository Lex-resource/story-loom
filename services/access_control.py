from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, WebSocket

from config import settings


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def is_local_host(host: str | None) -> bool:
    return bool(host and host in LOCAL_HOSTS)


def _presented_token(headers) -> str:
    token = headers.get("X-Remote-Access-Token", "")
    if token:
        return token
    authorization = headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _remote_token_is_valid(headers) -> bool:
    configured = settings.REMOTE_ACCESS_TOKEN.strip()
    presented = _presented_token(headers)
    return bool(configured and presented and secrets.compare_digest(presented, configured))


def require_local_request(request: Request) -> None:
    host = request.client.host if request.client else None
    if is_local_host(host):
        return
    if not settings.ALLOW_REMOTE_ACCESS:
        raise HTTPException(status_code=403, detail="Remote access is disabled")
    if not _remote_token_is_valid(request.headers):
        raise HTTPException(status_code=403, detail="Remote access token is required")


def websocket_access_allowed(websocket: WebSocket) -> bool:
    host = websocket.client.host if websocket.client else None
    if is_local_host(host):
        return True
    return settings.ALLOW_REMOTE_ACCESS and _remote_token_is_valid(websocket.headers)
