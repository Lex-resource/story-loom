"""生产与研究覆盖层之间的唯一接缝。

生产代码冻结在 A28/V43(见 `docs/research/novel-memory-continuity/PRODUCTION.md`),
因此**不含任何版本或变体字面量**。需要在研究运行里改变行为的生产函数,统一在这里
问一次 `research_override(...)`:拿到 `NO_OVERRIDE` 就执行自己内联的 A28/V43 逻辑。

三层短路,保证生产路径零开销、且可以完全不部署 `research/`:

1. 没有 `ExperimentContext` —— 普通生产运行,立即返回,不 import research
2. 有上下文但正好是生产冻结点(A28/V43)—— 同样让生产代码接管,使 pin A28/V43 的
   研究复现与生产走同一条路径
3. `research/` 不存在 —— 缓存该事实,后续直接返回

放在 `services/` 而非 `agents/`,是为了匹配既有导入方向:`agents/` 与 `worker_support/`
都已大量导入 `services/`。
"""
from __future__ import annotations

from typing import Any, Final

from services.experiment_recorder import current


class _NoOverride:
    """`research_override` 的哨兵返回值。

    不能用 `None` 或 `False` —— 部分表面(如 issue 分类判定)的合法覆盖值本身
    就是 `False`,用 falsy 值会把"无覆盖"和"覆盖为假"混在一起。
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return "NO_OVERRIDE"

    def __bool__(self) -> bool:
        return False


NO_OVERRIDE: Final = _NoOverride()

_research_unavailable = False


def research_override(surface: str, *args: Any, **kwargs: Any) -> Any:
    """研究覆盖值,或 `NO_OVERRIDE` 表示使用冻结的 A28/V43 生产行为。"""
    global _research_unavailable

    if _research_unavailable or current() is None:
        return NO_OVERRIDE

    try:
        from research.prompt_versions import resolve
    except ImportError:
        _research_unavailable = True
        return NO_OVERRIDE

    return resolve(surface, *args, **kwargs)


def reset_research_availability() -> None:
    """清除 `research/` 缺失的缓存标记。仅供测试使用。"""
    global _research_unavailable
    _research_unavailable = False
