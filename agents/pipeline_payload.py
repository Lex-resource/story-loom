from typing import Any


def bind_payload_fields(context, payload: dict[str, Any], mapping: dict[str, str]) -> None:
    for payload_key, context_attr in mapping.items():
        if payload_key in payload:
            setattr(context, context_attr, payload[payload_key])


def bind_truthy_payload_fields(context, payload: dict[str, Any], mapping: dict[str, str]) -> None:
    for payload_key, context_attr in mapping.items():
        if payload.get(payload_key):
            setattr(context, context_attr, payload[payload_key])
