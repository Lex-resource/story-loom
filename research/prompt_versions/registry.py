"""表面注册表。

单独成模块,避免各版本模块与 `research/prompt_versions/__init__.py` 之间的循环导入
——`__init__` 需要导入版本模块以触发注册,版本模块又需要 `register`。
"""
from __future__ import annotations

from typing import Any, Callable

from services.version_surface import NO_OVERRIDE

from research.prompt_versions.version_order import is_production_frozen_point

# 表面名 -> handler。handler 签名与生产调用点一致,返回覆盖值或 NO_OVERRIDE。
_HANDLERS: dict[str, Callable[..., Any]] = {}


def register(surface: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _HANDLERS[surface] = func
        return func

    return decorator


def resolve(surface: str, *args: Any, **kwargs: Any) -> Any:
    """解析一个表面。

    活动上下文就是生产冻结点(A28/V43)时一律让路——这保证 pin A28/V43 的研究
    复现与生产走同一条代码路径,而不是走一份可能漂移的副本。
    """
    if is_production_frozen_point():
        return NO_OVERRIDE

    handler = _HANDLERS.get(surface)
    if handler is None:
        return NO_OVERRIDE

    return handler(*args, **kwargs)


def registered_surfaces() -> tuple[str, ...]:
    """已注册的表面名。供测试断言覆盖面完整。"""
    return tuple(sorted(_HANDLERS))
