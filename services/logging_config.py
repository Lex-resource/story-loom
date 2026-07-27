from __future__ import annotations

import contextvars
import logging
import uuid


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_novel_logging_configured", False):
        return
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
    ))
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root._novel_logging_configured = True


def begin_request_context(value: str | None = None):
    return request_id_var.set(value or str(uuid.uuid4()))


def end_request_context(token) -> None:
    request_id_var.reset(token)
