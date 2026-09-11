from __future__ import annotations

import ipaddress
import socket
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from services.settings_constants import PROVIDER_TEST_MAX_TOKENS, PROVIDER_TEST_TIMEOUT_SECONDS
from services.settings_models import TestProviderRequest


import logging

logger = logging.getLogger(__name__)

__test__ = False


def validate_provider_base_url(base_url: str, *, resolve_dns: bool = True) -> str:
    """Validate a provider target before sending credentials to it."""
    value = base_url.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API 地址必须是 http 或 https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API 地址不得包含用户信息、查询参数或片段")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "local", "ip6-localhost"} or hostname.endswith(".localhost"):
        raise ValueError("API 地址必须指向公网主机")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = {literal}
    elif not resolve_dns:
        return value
    else:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            raise ValueError("API 地址无法解析")
    if not addresses or any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    ):
        raise ValueError("API 地址必须指向公网主机")
    return value


async def try_provider_request(
    method: str,
    base_url: str,
    endpoint: str,
    api_key: str,
    json_data: Optional[Dict] = None,
) -> Tuple[Dict[str, Any], str]:
    try:
        base_url = validate_provider_base_url(base_url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}, base_url.strip()
    api_key = api_key.strip()

    async def make_request(url: str):
        try:
            async with httpx.AsyncClient(
                timeout=PROVIDER_TEST_TIMEOUT_SECONDS,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                headers = {"Authorization": f"Bearer {api_key}"}
                if json_data:
                    headers["Content-Type"] = "application/json"

                if method.upper() == "GET":
                    response = await client.get(f"{url}{endpoint}", headers=headers)
                else:
                    response = await client.post(f"{url}{endpoint}", headers=headers, json=json_data)

                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    return {"ok": False, "error": "API response returned HTML instead of API data"}
                if response.status_code == 200:
                    try:
                        data = response.json()
                        return {"ok": True, "data": data}
                    except Exception as exc:
                        logger.warning(f"[Settings WARN] Failed to parse provider response JSON: {exc}")
                return {"ok": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    result = await make_request(base_url)
    if result["ok"]:
        return result, base_url

    if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        alt_url = base_url.rstrip("/") + "/v1"
        try:
            validate_provider_base_url(alt_url)
        except ValueError:
            return result, base_url
        alt_result = await make_request(alt_url)
        if alt_result["ok"]:
            return alt_result, alt_url

    return result, base_url


async def test_provider_connection_logic(req: TestProviderRequest) -> dict:
    if not req.base_url.strip() or not req.api_key.strip():
        return {"ok": False, "error": "请填写 API 地址和 Key"}

    json_data = {
        "model": req.model.strip(),
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": PROVIDER_TEST_MAX_TOKENS,
    }
    result, final_url = await try_provider_request(
        "POST",
        req.base_url,
        "/chat/completions",
        req.api_key,
        json_data,
    )

    if result["ok"]:
        data = result["data"]
        if isinstance(data, dict) and ("choices" in data or "error" in data):
            response = {"ok": True, "base_url": final_url}
            if final_url != req.base_url.strip():
                response["auto_corrected"] = True
            return response
        return {"ok": False, "error": "Invalid response format"}
    return result


test_provider_connection_logic.__test__ = False


def normalize_model_detail(item: dict[str, Any]) -> dict[str, Any]:
    model_id = item.get("id") or item.get("name") or item.get("model")
    context_length = (
        item.get("context_length")
        or item.get("max_context_length")
        or item.get("max_context_tokens")
        or item.get("input_token_limit")
        or item.get("max_input_tokens")
    )
    capabilities = (
        item.get("capabilities")
        or item.get("supported_generation_methods")
        or item.get("features")
        or item.get("modalities")
    )
    pricing = (
        item.get("pricing")
        or item.get("price")
        or item.get("prices")
        or item.get("billing")
    )
    return {
        "id": str(model_id) if model_id else "",
        "object": item.get("object"),
        "owned_by": item.get("owned_by") or item.get("owner"),
        "capabilities": capabilities,
        "context_length": context_length,
        "input_token_limit": item.get("input_token_limit") or item.get("max_input_tokens"),
        "output_token_limit": item.get("output_token_limit") or item.get("max_output_tokens"),
        "pricing": pricing,
        "raw": item,
    }


async def list_models_by_provider_logic(base_url: str, api_key: str) -> dict:
    if not api_key.strip():
        return {"ok": False, "error": "请填写 API Key", "models": [], "model_details": {}}

    result, final_url = await try_provider_request("GET", base_url, "/models", api_key)

    if result["ok"]:
        data = result["data"]
        if isinstance(data, dict) and "data" in data:
            details = {}
            models = []
            for item in data.get("data", []):
                if not isinstance(item, dict):
                    continue
                detail = normalize_model_detail(item)
                model_id = detail.get("id")
                if not model_id:
                    continue
                models.append(model_id)
                details[model_id] = detail
            response = {"ok": True, "models": models, "model_details": details, "base_url": final_url}
            if final_url != base_url.strip():
                response["auto_corrected"] = True
            return response
        return {"ok": False, "error": "Invalid response format"}

    result["models"] = []
    result["model_details"] = {}
    return result
