from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket

from config import settings


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def is_local_host(host: str | None) -> bool:
    return bool(host and host in LOCAL_HOSTS)


def require_local_request(request: Request) -> None:
    if settings.ALLOW_REMOTE_ACCESS:
        return
    host = request.client.host if request.client else None
    if not is_local_host(host):
        raise HTTPException(status_code=403, detail="Remote access is disabled")


def websocket_access_allowed(websocket: WebSocket) -> bool:
    if settings.ALLOW_REMOTE_ACCESS:
        return True
    host = websocket.client.host if websocket.client else None
    return is_local_host(host)
