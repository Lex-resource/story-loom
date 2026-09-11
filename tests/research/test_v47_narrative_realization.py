from research.prompt_versions.hints import (
    v47_narrative_realization_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v47-narrative-realization",
        prompt_version="V47",
        variant="ariadne-a33-v47-narrative-realization",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )


def test_v47_is_recognized_and_keeps_v46_as_parent(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V46")
        assert prompt_version_at_least("V47")
        assert "V46 戏剧转折" in v47_narrative_realization_hint("writer")
    finally:
        deactivate(token)


def test_v47_pushes_concrete_prose_without_turning_style_into_a_retry(tmp_path):
    token = activate(_context(tmp_path))
    try:
        writer_hint = v47_narrative_realization_hint("writer")
        editor_hint = v47_narrative_realization_hint("editor")
        validator_hint = v47_narrative_realization_hint("validator")

        assert "只作幕后路线" in writer_hint
        assert "具体细节替代" in writer_hint
        assert "不得仅因文风问题要求 Writer 重写" in editor_hint
        assert "不得单独触发 Writer 重写" in validator_hint
        assert "只有事实、时间线、地点、物品、角色状态、核心事件等硬冲突才 block" in validator_hint
    finally:
        deactivate(token)


def test_v47_exposes_marker_to_all_writing_agents(tmp_path):
    token = activate(_context(tmp_path))
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            assert "V47 叙事落地" in v47_narrative_realization_hint(agent_type)
    finally:
        deactivate(token)
