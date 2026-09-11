"""提示词作用域测试。

自定义工作流的三种诉求都压在这一个接缝上：复用别人的提示词（换 category）、
给某步换一份提示词（换名字）、同一角色多次出场各用不同提示词（逐步骤生效）。

**最要紧的一条**：作用域为空时必须原样透传 —— 长篇（以及所有没有自定义节点的工作流）
的提示词解析路径不能有任何变化，否则 V43 黄金快照之外的行为会悄悄漂移。
"""
from __future__ import annotations

import asyncio

import pytest

from services import prompt_scope
from services.prompt_scope import EMPTY_SCOPE, PromptScope, resolve
from services.workflow_nodes import (
    ROLE_PRIMARY_PROMPT,
    WorkflowNode,
    builtin_node_id,
    default_catalog,
    prompt_overrides_for,
    resolve_node,
)
from services.pipeline_stages import (
    ROLE_POST_EDIT,
    ROLE_PRE_EDITOR,
    ROLE_REVIEW,
    ROLE_STYLE_REPAIR,
)


def test_empty_scope_passes_through():
    """长篇路径：一个字都不许改。"""
    assert resolve("editor_review", "long_webnovel") == ("editor_review", "long_webnovel")


def test_scope_is_empty_by_default():
    assert prompt_scope.current() is EMPTY_SCOPE
    assert EMPTY_SCOPE.is_empty()


def test_name_override():
    with prompt_scope.scoped(PromptScope(names={"editor_destyle": "polish_colloquial"})):
        assert resolve("editor_destyle", "zhihu_short") == (
            "polish_colloquial",
            "zhihu_short",
        )
        # 表里没有的名字原样透传
        assert resolve("editor_review", "zhihu_short") == ("editor_review", "zhihu_short")


def test_category_override():
    """「复用别人的提示词」：只换 category，名字不动。"""
    with prompt_scope.scoped(PromptScope(category="long_webnovel")):
        assert resolve("writer", "custom_thriller") == ("writer", "long_webnovel")


def test_both_overrides_compose():
    scope = PromptScope(category="long_webnovel", names={"writer": "writer_terse"})
    with prompt_scope.scoped(scope):
        assert resolve("writer", "custom") == ("writer_terse", "long_webnovel")


def test_scope_restores_on_exit():
    with prompt_scope.scoped(PromptScope(category="a")):
        with prompt_scope.scoped(PromptScope(category="b")):
            assert resolve("x", "orig")[1] == "b"
        assert resolve("x", "orig")[1] == "a"
    assert resolve("x", "orig")[1] == "orig"


def test_scope_restores_after_exception():
    with pytest.raises(RuntimeError):
        with prompt_scope.scoped(PromptScope(category="boom")):
            raise RuntimeError("boom")
    assert prompt_scope.current() is EMPTY_SCOPE


def test_scope_is_isolated_across_concurrent_tasks():
    """并发生成多个章节时不能串 —— 这是选 contextvar 而不是全局变量的理由。"""

    async def run(category: str, hold: float) -> str:
        with prompt_scope.scoped(PromptScope(category=category)):
            await asyncio.sleep(hold)
            return resolve("writer", "orig")[1]

    async def main():
        return await asyncio.gather(run("a", 0.02), run("b", 0.0), run("c", 0.01))

    assert asyncio.run(main()) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 节点 -> 覆盖表
# ---------------------------------------------------------------------------


def test_builtin_node_yields_no_override():
    """内置节点不产生覆盖 —— 于是作用域为空，长篇路径不变。"""
    for node in default_catalog().values():
        assert prompt_overrides_for(node) == {}


def test_none_node_yields_no_override():
    assert prompt_overrides_for(None) == {}


def test_custom_node_overrides_its_roles_primary_prompt():
    node = WorkflowNode(
        id="editor.style_repair.colloquial",
        name_zh="口语化重写",
        role=ROLE_STYLE_REPAIR,
        prompt_name="polish_colloquial",
    )
    assert prompt_overrides_for(node) == {"editor_destyle": "polish_colloquial"}


def test_node_naming_its_own_builtin_prompt_yields_no_override():
    """显式填了内置提示词名等于没换 —— 别产生一条 a->a 的映射，那会让作用域非空。"""
    node = WorkflowNode(
        id="x", name_zh="x", role=ROLE_REVIEW, prompt_name=ROLE_PRIMARY_PROMPT[ROLE_REVIEW]
    )
    assert prompt_overrides_for(node) == {}


def test_validator_roles_share_a_builtin_prompt_but_overrides_stay_per_step():
    """三个 validator 角色共用同一个内置提示词名。

    覆盖是逐步骤生效的（解释器每步单独开作用域），所以只给编辑后校验换提示词
    不会连带改掉前置校验和终审 —— 否则「换一步」就成了「换三步」。
    """
    assert (
        ROLE_PRIMARY_PROMPT[ROLE_PRE_EDITOR]
        == ROLE_PRIMARY_PROMPT[ROLE_POST_EDIT]
        == ROLE_PRIMARY_PROMPT["final"]
    )
    post_only = WorkflowNode(
        id="validator.post_edit.strict", name_zh="严格后校验",
        role=ROLE_POST_EDIT, prompt_name="validator_strict",
    )
    overrides = prompt_overrides_for(post_only)
    assert overrides == {"validator_validate_content": "validator_strict"}
    # 只在这一步的作用域里生效
    with prompt_scope.scoped(PromptScope(names=overrides)):
        assert resolve("validator_validate_content", "f")[0] == "validator_strict"
    assert resolve("validator_validate_content", "f")[0] == "validator_validate_content"


# ---------------------------------------------------------------------------
# 节点解析
# ---------------------------------------------------------------------------


def test_resolve_node_falls_back_to_builtin_for_empty_id():
    catalog = default_catalog()
    node = resolve_node(None, ROLE_REVIEW, catalog)
    assert node is not None and node.id == builtin_node_id(ROLE_REVIEW)


def test_resolve_node_falls_back_when_id_is_missing():
    """手工改库删掉了一个仍被引用的节点，也不能让那个工作流的生成直接失败。"""
    catalog = default_catalog()
    node = resolve_node("ghost.node", ROLE_STYLE_REPAIR, catalog)
    assert node is not None and node.id == builtin_node_id(ROLE_STYLE_REPAIR)


def test_resolve_node_uses_default_catalog_when_none_given():
    node = resolve_node(None, ROLE_REVIEW, None)
    assert node is not None and node.role == ROLE_REVIEW


def test_builtin_node_ids_match_migration_seed():
    """节点 id 必须与迁移里的种子一致，否则默认图引用的节点全查不到。"""
    expected = {
        "planner.outline",
        "system.context_refresh",
        "writer.draft",
        "validator.pre_editor",
        "editor.review",
        "editor.force_revise",
        "validator.post_edit",
        "editor.style_repair",
        "validator.final",
        "system.publish",
        "extractor.postprocess",
    }
    assert set(default_catalog()) == expected


def test_agent_base_resolves_prompt_exactly_once(monkeypatch):
    """CLAUDE.md 的约束升级为测试:resolve 在缓存加载之前,恰好调用一次。

    套两次 resolve 会在病态映射下翻回去(见 agents/prompt_templates 的
    load_prompt_template docstring),这里守住"只解析一次"这条线。
    """
    from types import SimpleNamespace

    from agents import base as agents_base

    calls = []
    real_resolve = agents_base.resolve_prompt_ref

    def counting_resolve(name, category):
        calls.append((name, category))
        return real_resolve(name, category)

    async def fake_load(name, *, category):
        return (f"system:{name}", f"user:{category}")

    monkeypatch.setattr(agents_base, "resolve_prompt_ref", counting_resolve)
    monkeypatch.setattr(agents_base, "load_prompt_template", fake_load)
    monkeypatch.setattr(agents_base, "record_prompt_template", lambda **kwargs: None)

    dummy = SimpleNamespace()
    system_prompt, user_prompt = asyncio.run(
        agents_base.AgentBase.get_prompt_template(dummy, "editor_review", category="long_webnovel")
    )

    assert calls == [("editor_review", "long_webnovel")]
    assert system_prompt == "system:editor_review"
    assert dummy.active_prompt_name == "editor_review (long_webnovel)"
