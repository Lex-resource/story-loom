"""生产工作流之间的唯一接缝(格式轴)。

`services/version_surface.py` 管的是**研究版本轴**:同一套工作流在 V43/V50/V66 下
表面不同。本模块管的是**格式轴**:长篇与短篇是两套工作流,表面本就不该相同。

两条轴正交叠加。调用点先问版本轴、再问格式轴(见 `agents/prompt_hints.generation_hints`),
于是:研究实验仍可覆盖任意工作流,而普通短篇生产**不需要 `research/` 存在**也能拿到
短篇表面 —— 短篇不是研究变体,它是一等生产工作流。

生产冻结在 A28/V43 的只有**长篇**(见 `docs/research/novel-memory-continuity/PRODUCTION.md`)。
因此 `long_webnovel` 一律返回 `NO_WORKFLOW_OVERRIDE`,让调用点执行自己内联的 A28/V43
逻辑 —— 长篇提示词字节不变,`tests/test_v43_production_surface_snapshot.py` 的黄金快照
不动。这是「把短篇分出去」,不是「改写长篇」。

放在 `services/` 而非 `agents/`,与 `version_surface` 同一个理由:消费者同时来自
`agents/`(prompt_hints)、`services/`(chapter_continuity、quality_metrics)和
`worker_support/`,而这三者都已大量导入 `services/`。
"""
from __future__ import annotations

from typing import Any, Callable, Final

from services import workflow_registry as registry


class _NoWorkflowOverride:
    """`workflow_override` 的哨兵返回值。

    与 `version_surface.NO_OVERRIDE` 同理,不能用 `None` 或 `False`:部分表面的
    合法工作流覆盖值本身就是假值(`editor_policy` 的布尔开关、被短篇刻意清空的
    hint 字符串),用假值会把「无覆盖」和「覆盖为假」混在一起。
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return "NO_WORKFLOW_OVERRIDE"

    def __bool__(self) -> bool:
        return False


NO_WORKFLOW_OVERRIDE: Final = _NoWorkflowOverride()


# 表面策略名。工作流记录(`pipeline_configs.surface_strategy`)存的就是这些值。
# 定义在 `workflow_registry`（缓存那一层需要它们做兜底映射），这里重新导出，
# 让「表面」的消费者不必知道缓存的存在。
STRATEGY_FROZEN_V43: Final = registry.STRATEGY_FROZEN_V43
STRATEGY_SHORT_FORM: Final = registry.STRATEGY_SHORT_FORM
STRATEGY_CUSTOM: Final = registry.STRATEGY_CUSTOM

# (策略, 表面名) -> handler。handler 签名与生产调用点一致。
_HANDLERS: dict[tuple[str, str], Callable[..., Any]] = {}


def register(strategy: str, surface: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """把一个 handler 注册为某策略下某表面的实现。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _HANDLERS[(strategy, surface)] = func
        return func

    return decorator


def strategy_for(novel_format: str | None) -> str:
    """该工作流使用的表面策略。

    权威来源是 `pipeline_configs.surface_strategy`，经 `workflow_registry` 的进程内
    缓存同步读取（表面函数在提示词组装的热路径上，不能有 I/O）。缓存冷时回落到两个
    内置工作流的静态映射，所以长篇与短篇不依赖缓存是否已预热。

    未知工作流按长篇冻结点处理 —— 保守，不擅自改表面。
    """
    return registry.strategy_for(novel_format)


def is_short_form_workflow(novel_format: str | None) -> bool:
    """该工作流是否走短篇表面。

    取代散落在 5 处的 `novel_format == NOVEL_FORMAT_ZHIHU_SHORT` 硬判断
    （Editor 的输出 schema、完结全文审校、记忆合并、创作画像推断、策略兜底）。
    那些判断按格式名硬比时，从短篇克隆出来的自定义工作流会拿到短篇提示词却走长篇
    的 schema 与记忆合并 —— 提示词对了、结构错了，是最难查的一类静默错误。
    """
    return strategy_for(novel_format) == STRATEGY_SHORT_FORM


def workflow_override(surface: str, novel_format: str | None, *args: Any, **kwargs: Any) -> Any:
    """该工作流对某表面的覆盖值,或 `NO_WORKFLOW_OVERRIDE` 表示用调用点的内联逻辑。

    `frozen_v43`(长篇及一切未知格式)永远让路,因此长篇不经过任何新代码路径。
    """
    strategy = strategy_for(novel_format)
    if strategy == STRATEGY_FROZEN_V43:
        return NO_WORKFLOW_OVERRIDE

    handler = _HANDLERS.get((strategy, surface))
    if handler is None:
        # 该策略没有实现这个表面 —— 让路到冻结逻辑,而不是报错。新增表面时
        # 长篇立即可用,短篇按需逐个接管。
        return NO_WORKFLOW_OVERRIDE

    return handler(*args, **kwargs)


def registered_surfaces() -> tuple[tuple[str, str], ...]:
    """已注册的 (策略, 表面) 对。供测试断言覆盖面完整。"""
    return tuple(sorted(_HANDLERS))


# 导入短篇表面实现以触发注册。放在文件末尾,避免 `short_form_surfaces` 导入
# 本模块的 `register`/策略常量时形成循环 —— 与 `research/prompt_versions/__init__.py`
# 末尾导入各版本模块是同一个手法。
from services import short_form_surfaces as _short_form_surfaces  # noqa: E402,F401
