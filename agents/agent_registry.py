"""Agent name vocabulary and the default-agent registry.

从 agents/constants.py 拆出:agent 名是跨层词汇(services/worker_support/routers
都要用),注册表是 agents 层自有的装配逻辑 —— 两者内聚点不同,不该住同一文件。
constants.py 仍然再导出全部名字,现有 `from agents.constants import AGENT_*`
不需要改。
"""

# Canonical agent / pipeline node names.
# Used by: agents/pipeline.py, worker_support/*, services/*,
# routers/settings.py, frontend store.
AGENT_PLANNER = "planner"
AGENT_WRITER = "writer"
AGENT_EDITOR = "editor"
AGENT_VALIDATOR = "validator"
AGENT_EXTRACTOR = "extractor"
AGENT_CHARACTER_CARD = "character_card"
# 记忆整合不是流水线节点，只是 post-processing 里的辅助调用；
# 独立命名是为了 usage 统计里能区分整合成本，不与 extractor 混算。
AGENT_SCENE_CONSOLIDATOR = "scene_consolidator"

# 五个 agent 的规范顺序在 `services/pipeline_stages.CANONICAL_AGENT_ORDER` —— 它同时是
# `PipelineStep` 顺序的派生依据，所以那里是唯一来源。这里不再放第二份同样的列表。

# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------
# Maps agent name -> zero-arg factory callable that returns a default AgentBase
# instance. PipelineNode subclasses look up their default agent here instead of
# hard-coding `_default_planner()` etc., so adding a new agent only requires
# registering a factory in one place.
#
# Factories are stored as lazy strings+callables to avoid importing every agent
# class at module load time (which would create circular imports because agents
# import from agents.constants).

_AGENT_REGISTRY: dict[str, "callable"] = {}

# Whether _bootstrap_default_agents() has been invoked yet.
#
# Bootstrap MUST be lazy: doing it at module load creates a circular import
# (agents.constants -> agents.writing.* -> agents.base -> agents.constants)
# that fails because agents.base.AgentBase is not yet defined when the
# writing-agent modules try to import it. Triggering on first
# get_default_agent() call defers the writing-agent imports until *all* of
# agents.base has finished loading, which breaks the cycle.
_AGENT_BOOTSTRAP_DONE: bool = False


def register_agent(name: str, factory: "callable") -> None:
    """Register a default-agent factory under the given agent name.

    Idempotent: re-registering the same name overwrites the previous factory.
    """
    _AGENT_REGISTRY[name] = factory


def get_default_agent(name: str):
    """Return a fresh default agent instance for *name*.

    Triggers :func:`_bootstrap_default_agents` on first call to populate the
    built-in agent factories. Raises ``KeyError`` if *name* is not a registered
    agent.
    """
    global _AGENT_BOOTSTRAP_DONE
    if not _AGENT_BOOTSTRAP_DONE:
        _bootstrap_default_agents()
        _AGENT_BOOTSTRAP_DONE = True
    if name not in _AGENT_REGISTRY:
        raise KeyError(
            f"No default agent factory registered for {name!r}. "
            f"Call register_agent({name!r}, factory) first. "
            f"Known agents: {sorted(_AGENT_REGISTRY)}"
        )
    return _AGENT_REGISTRY[name]()


def _bootstrap_default_agents() -> None:
    """Register the built-in default agent factories.

    Imports are local to keep this module free of circular dependencies.
    Triggered lazily on first :func:`get_default_agent` call (not at module
    load) so that agents.base is fully loaded by the time the writing-agent
    modules need to import ``AgentBase`` from it.
    """
    from agents.writing.planner import PlannerAgent
    from agents.writing.writer import WriterAgent
    from agents.writing.editor import EditorAgent
    from agents.writing.validator_agent import ValidatorAgent
    from agents.writing.extractor import ExtractorAgent

    register_agent(AGENT_PLANNER, PlannerAgent)
    register_agent(AGENT_WRITER, WriterAgent)
    register_agent(AGENT_EDITOR, EditorAgent)
    register_agent(AGENT_VALIDATOR, ValidatorAgent)
    register_agent(AGENT_EXTRACTOR, ExtractorAgent)


# NOTE: _bootstrap_default_agents() is intentionally NOT called at module load.
# It is triggered lazily by get_default_agent() on first use. Calling it here
# creates a circular import (agents.constants -> agents.writing.* ->
# agents.base -> agents.constants) that fails because AgentBase is not yet
# defined when the writing-agent modules try to import it. See the comment on
# _AGENT_BOOTSTRAP_DONE above for the full rationale.
