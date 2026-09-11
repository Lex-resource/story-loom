from pathlib import Path

import pytest

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v63_chapter_closure_hint,
    v64_cross_chapter_stage_transition_hint,
)
from agents.pipeline_context import PipelineContext
from agents.writing.writer import WriterAgent
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v64-cross-chapter-stage-transition",
            prompt_version="V64",
            variant="ariadne-a50-v64-cross-chapter-stage-transition",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v64_dispatches_after_v63_without_mutating_archived_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V63")
        assert prompt_version_at_least("V64")
        dispatched = v54_intra_chapter_action_repair_hint("writer")
        direct = v64_cross_chapter_stage_transition_hint("writer")
        assert dispatched == direct
        assert "V64 跨章阶段切换" in direct
        assert "V64 跨章阶段切换" not in v63_chapter_closure_hint("writer")
    finally:
        deactivate(token)


def test_v64_requires_an_explicit_new_stage_boundary_for_each_agent(tmp_path):
    token = _activate(tmp_path)
    try:
        hints = {
            agent: v64_cross_chapter_stage_transition_hint(agent)
            for agent in ("planner", "writer", "editor", "validator", "extractor")
        }
    finally:
        deactivate(token)

    assert "已完成动作" in hints["planner"]
    assert "本章第一段之后必须出现" in hints["writer"]
    assert "new_stage_delta" in hints["editor"]
    assert "结尾至少有一个与上一章不同" in hints["validator"]
    assert "inherited/replayed" in hints["extractor"]


@pytest.mark.asyncio
async def test_writer_clears_stale_raw_handoff_before_rendering():
    token = activate(
        ExperimentContext(
            run_id="v64-writer-context-boundary",
            prompt_version="V64",
            variant="ariadne-a50-v64-cross-chapter-stage-transition",
            project_id="project",
            chapter_index=5,
            root_dir=Path("."),
        )
    )
    context = PipelineContext(
        project_id="project",
        chapter_index=5,
        novel_format="long_webnovel",
        chapter_outline={"chapter_index": 5, "title": "测试章"},
        chapter_handoff_context="旧 Worker 误带入的完整交接包",
        chapter_contract_context="旧 Worker 误带入的完整契约",
        writer_execution_brief_context='{"opening": {"previous_terminal_state": "已完成"}}',
    )
    agent = WriterAgent.__new__(WriterAgent)

    async def fake_get_prompt_template(*_args, **_kwargs):
        return "system", "user"

    async def fake_call_llm(*_args, **_kwargs):
        return "正文"

    agent.get_prompt_template = fake_get_prompt_template
    agent.call_llm = fake_call_llm

    try:
        result = await agent.write_chapter(context)
    finally:
        deactivate(token)

    assert result == "正文"
    assert context.chapter_handoff_context == ""
    assert context.chapter_contract_context == ""
