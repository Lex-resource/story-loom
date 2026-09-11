"""S8 回归测试：进程级共享 HTTP client 的复用与关闭重建。"""
import asyncio
import ssl

import pytest

from services import shared_http


@pytest.fixture(autouse=True)
def _shared_ssl_context(monkeypatch):
    """复用一个预建 SSLContext：真实构造每次都重载整个 certifi CA bundle
    （httpx SSLConfig → load_verify_locations），单用例 ~1s，纯测试开销，
    与本文件要验证的复用/关闭重建语义无关。"""
    ctx = ssl.create_default_context()
    # 注意 patch 使用点:default.py 是 `from .._config import create_ssl_context`
    # 把函数绑进了自己的命名空间,patch 源模块不影响已绑定的引用。
    # patch 目标是 httpx 私有符号(_transports.default),httpx 已 pin 0.27.0;
    # 升级 httpx 后需确认此 patch 仍命中——失效不报错,只会让测试悄悄变慢。
    monkeypatch.setattr(
        "httpx._transports.default.create_ssl_context", lambda **_kwargs: ctx
    )
    yield


@pytest.fixture(autouse=True)
def _reset_client():
    shared_http._client = None
    yield
    if shared_http._client is not None and not shared_http._client.is_closed:
        asyncio.run(shared_http._client.aclose())
    shared_http._client = None


def test_same_client_reused():
    first = shared_http.get_shared_client()
    second = shared_http.get_shared_client()
    assert first is second


def test_close_produces_fresh_client():
    first = shared_http.get_shared_client()
    asyncio.run(shared_http.close_shared_client())
    second = shared_http.get_shared_client()

    assert first is not second
    assert first.is_closed
    assert not second.is_closed
