import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.constants import PROMPT_SCENE_BLOCK_CONSOLIDATION


ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_FILES = (
    ROOT / "prompts" / "extraction" / "long_webnovel_extraction.json",
    ROOT / "prompts" / "extraction" / "zhihu_short_extraction.json",
)


def test_scene_block_consolidation_template_registered_for_both_formats():
    for path in EXTRACTION_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        match = [item for item in data if item.get("name") == PROMPT_SCENE_BLOCK_CONSOLIDATION]
        assert len(match) == 1, f"{path.name} 缺少场景块整合模板"
        template = match[0]
        assert template["category"] in ("long_webnovel", "zhihu_short")
        assert "{chapter_tail}" in template["user_prompt_template"]
        assert "{accepted_atoms}" in template["user_prompt_template"]


def test_consolidator_agent_uses_consolidation_model(monkeypatch):
    from config import settings
    from agents.scene_consolidator_agent import SceneConsolidatorAgent

    monkeypatch.setattr(settings, "CONSOLIDATION_MODEL", "cheap-consolidation-model")
    agent = SceneConsolidatorAgent()
    assert agent.model == "cheap-consolidation-model"

    monkeypatch.setattr(settings, "CONSOLIDATION_MODEL", "")
    fallback_agent = SceneConsolidatorAgent()
    assert fallback_agent.model is None


@pytest.mark.asyncio
async def test_consolidate_scene_summary_extracts_summary(monkeypatch):
    from agents.scene_consolidator_agent import SceneConsolidatorAgent

    agent = SceneConsolidatorAgent()

    async def _fake_template(name, *, category):
        return "系统提示", "章节:{chapter_title} 大纲:{outline_summary} 事实:{accepted_atoms} 结尾:{chapter_tail}"

    async def _fake_call(system_prompt, user_prompt, *args, **kwargs):
        return {"summary": "主角取得潮汐记录，守军开始怀疑塔内异常。"}

    agent.get_prompt_template = _fake_template
    agent.call_llm_json = _fake_call

    summary = await agent.consolidate_scene_summary(
        novel_format="long_webnovel",
        chapter_title="回执",
        chapter_tail="林照推开档案室的门。",
        accepted_atoms=["林照持有第九次潮汐记录副本"],
        outline_summary="调查推进",
    )
    assert summary == "主角取得潮汐记录，守军开始怀疑塔内异常。"


@pytest.mark.asyncio
async def test_consolidate_scene_summary_returns_empty_on_blank_output():
    from agents.scene_consolidator_agent import SceneConsolidatorAgent

    agent = SceneConsolidatorAgent()

    async def _fake_template(name, *, category):
        return "系统提示", "模板"

    async def _fake_call(system_prompt, user_prompt, *args, **kwargs):
        return {"summary": "  "}

    agent.get_prompt_template = _fake_template
    agent.call_llm_json = _fake_call

    assert await agent.consolidate_scene_summary(
        novel_format="long_webnovel",
        chapter_title="回执",
        chapter_tail="结尾",
        accepted_atoms=[],
        outline_summary="",
    ) == ""


@pytest.mark.asyncio
async def test_consolidation_falls_back_on_failure():
    from types import SimpleNamespace as _NS

    import agents.scene_consolidator_agent as module
    from services.novel_memory_consolidation import consolidate_scene_summary

    class _BrokenAgent:
        def __init__(self):
            raise RuntimeError("no provider")

    original = module.SceneConsolidatorAgent
    module.SceneConsolidatorAgent = _BrokenAgent
    try:
        novel = _NS(id="p", novel_format="long_webnovel")
        chapter = _NS(title="回执", chapter_index=3, content="正文")
        summary = await consolidate_scene_summary(
            None, novel, chapter, "大纲摘要", []
        )
    finally:
        module.SceneConsolidatorAgent = original
    assert summary == ""
