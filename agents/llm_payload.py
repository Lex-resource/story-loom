import json
from pathlib import Path
from typing import Optional


def build_llm_payload(
    current_model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    response_format: Optional[dict],
) -> dict:
    payload = {
        "model": current_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    return payload


def debug_log_payload(
    json_payload: dict,
    system_prompt: str,
    user_prompt: str,
    current_model: str,
    *,
    debug_enabled: bool,
    log_dir: str,
    size_threshold: int,
) -> None:
    if not debug_enabled:
        return

    payload_size_bytes = len(json.dumps(json_payload, ensure_ascii=False).encode("utf-8"))
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    with open(log_path / "payload_debug.log", "a", encoding="utf-8") as f:
        f.write(
            f"\n[DEBUG-PAYLOAD] ========== 发送给 {current_model} 的请求包大小: "
            f"{payload_size_bytes} 字节 ({payload_size_bytes/1024/1024:.3f} MB) ==========\n"
        )
        f.write(f"  - system_prompt 长度: {len(system_prompt)} 字符\n")
        f.write(f"  - user_prompt 长度: {len(user_prompt)} 字符\n")
    if payload_size_bytes > size_threshold:
        with open(log_path / "huge_payload.json", "w", encoding="utf-8") as f:
            json.dump(json_payload, f, ensure_ascii=False)
