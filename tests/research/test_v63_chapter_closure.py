from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v62_stage_breakthrough_hint,
    v63_chapter_closure_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v63-chapter-closure",
            prompt_version="V63",
            variant="ariadne-a49-v63-chapter-closure",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v63_dispatches_after_v62_without_mutating_archived_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V62")
        assert prompt_version_at_least("V63")
        dispatched = v54_intra_chapter_action_repair_hint("writer")
        direct = v63_chapter_closure_hint("writer")
        assert dispatched == direct
        assert "V63 章节闭环" in direct
        assert "V63 章节闭环" not in v62_stage_breakthrough_hint("writer")
    finally:
        deactivate(token)


def test_v63_requires_a_bounded_result_for_each_agent(tmp_path):
    token = _activate(tmp_path)
    try:
        hints = {agent: v63_chapter_closure_hint(agent) for agent in ("planner", "writer", "editor", "validator", "extractor")}
    finally:
        deactivate(token)

    assert "可在本章结尾判定的局部目标" in hints["planner"]
    assert "成功、失败、现实代价" in hints["writer"]
    assert "局部叙事修复" in hints["editor"]
    assert "可定位的局部目标" in hints["validator"]
    assert "被行动排除的具体条件" in hints["extractor"]
