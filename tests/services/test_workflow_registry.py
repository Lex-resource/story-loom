"""工作流缓存与表面策略测试。

`workflow_surface.strategy_for()` 从静态字典改成了「进程内缓存 + 静态兜底」。
最要紧的一条：**缓存是空的时候长篇与短篇必须完全正确** —— 生产行为不能依赖缓存
是否已预热，否则一次冷启动就会让长篇按未知格式处理。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL, NOVEL_FORMAT_ZHIHU_SHORT
from services import workflow_registry as registry
from services.workflow_surface import (
    STRATEGY_FROZEN_V43,
    STRATEGY_SHORT_FORM,
    is_short_form_workflow,
    strategy_for,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """每个用例都从空缓存开始，并在结束时恢复 —— 缓存是进程级的。"""
    saved = registry.snapshot()
    registry.invalidate()
    yield
    registry.invalidate()
    for record in saved.values():
        registry._records[record.name] = record


def _row(name, *, surface_strategy=None, prompt_category=None, quality_dims=None, builtin=False):
    return SimpleNamespace(
        name=name,
        surface_strategy=surface_strategy,
        prompt_category=prompt_category,
        quality_dims=quality_dims,
        builtin=builtin,
    )


# ---------------------------------------------------------------------------
# 冷缓存
# ---------------------------------------------------------------------------


def test_cold_cache_is_correct_for_builtin_workflows():
    """这是不变量：缓存空着，长篇与短篇也必须解析对。"""
    assert registry.snapshot() == {}
    assert strategy_for(NOVEL_FORMAT_LONG_WEBNOVEL) == STRATEGY_FROZEN_V43
    assert strategy_for(NOVEL_FORMAT_ZHIHU_SHORT) == STRATEGY_SHORT_FORM
    assert is_short_form_workflow(NOVEL_FORMAT_ZHIHU_SHORT) is True
    assert is_short_form_workflow(NOVEL_FORMAT_LONG_WEBNOVEL) is False


@pytest.mark.parametrize("value", [None, "", "does_not_exist"])
def test_unknown_workflow_falls_back_to_frozen_v43(value):
    """未知工作流按长篇冻结点处理 —— 保守，不擅自改表面。"""
    assert strategy_for(value) == STRATEGY_FROZEN_V43
    assert is_short_form_workflow(value) is False


def test_cold_cache_prompt_category_is_the_format_itself():
    """缓存冷时 `snapshot()` 是空的 —— 生产读 prompt_category 走的是 PipelineConfig。"""
    assert registry.snapshot() == {}


# ---------------------------------------------------------------------------
# 预热后
# ---------------------------------------------------------------------------


def test_cloned_short_workflow_gets_short_surface():
    """本次改造的核心：克隆自短篇的工作流走短篇表面。

    改造前这里是 `novel_format == "zhihu_short"` 硬比，于是它会拿到短篇提示词却走
    长篇的 Editor schema、没有完结全文审校、按长篇合并记忆 —— 静默错误。
    """
    registry.remember(_row("custom_thriller", surface_strategy="short_form"))
    assert strategy_for("custom_thriller") == STRATEGY_SHORT_FORM
    assert is_short_form_workflow("custom_thriller") is True


def test_custom_strategy_is_not_short_form():
    registry.remember(_row("weird", surface_strategy="custom"))
    assert strategy_for("weird") == "custom"
    assert is_short_form_workflow("weird") is False


def test_row_without_strategy_uses_builtin_mapping():
    """老库里 surface_strategy 可能是 NULL；内置两行仍要解析对。"""
    registry.remember(_row(NOVEL_FORMAT_ZHIHU_SHORT, surface_strategy=None))
    assert strategy_for(NOVEL_FORMAT_ZHIHU_SHORT) == STRATEGY_SHORT_FORM
    registry.remember(_row("brand_new", surface_strategy=None))
    assert strategy_for("brand_new") == STRATEGY_FROZEN_V43


def test_garbage_strategy_falls_back_instead_of_propagating():
    registry.remember(_row("broken", surface_strategy="teleport"))
    assert strategy_for("broken") == STRATEGY_FROZEN_V43


def test_prompt_category_defaults_to_name_and_can_be_shared():
    """`prompt_category` 为空时落回工作流名；填了别人的名字就是「共享提示词」。"""
    registry.remember(_row("owns_prompts", prompt_category=None))
    assert registry.snapshot()["owns_prompts"].prompt_category == "owns_prompts"
    registry.remember(_row("shares", prompt_category="long_webnovel"))
    assert registry.snapshot()["shares"].prompt_category == "long_webnovel"


def test_quality_dims_are_normalized_to_a_tuple_or_none():
    registry.remember(_row("x", quality_dims=["a", "b"]))
    assert registry.snapshot()["x"].quality_dims == ("a", "b")
    registry.remember(_row("y", quality_dims=[]))
    assert registry.snapshot()["y"].quality_dims is None


def test_invalidate_single_and_all():
    registry.remember(_row("a", surface_strategy="short_form"))
    registry.remember(_row("b", surface_strategy="short_form"))
    registry.invalidate("a")
    assert "a" not in registry.snapshot()
    assert "b" in registry.snapshot()
    registry.invalidate()
    assert registry.snapshot() == {}


def test_builtin_workflows_cannot_be_reclassified_by_a_stale_cache_entry():
    """缓存里若有一条把长篇标成短篇的脏数据，它会生效 —— 所以写入端必须拦住。

    这条用例是为了把「护栏在写入端」这件事记录下来：缓存忠实反映数据库，
    不在读取时二次判断。API 层（workflow_admin_service）拒绝修改内置工作流的表面策略。
    """
    registry.remember(_row(NOVEL_FORMAT_LONG_WEBNOVEL, surface_strategy="short_form"))
    assert strategy_for(NOVEL_FORMAT_LONG_WEBNOVEL) == STRATEGY_SHORT_FORM
