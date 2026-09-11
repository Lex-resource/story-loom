from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v58_structured_character_turn_hint,
    v59_action_first_realization_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v59-action-first-realization",
            prompt_version="V59",
            variant="ariadne-a45-v59-action-first-realization",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v59_registers_after_v58_and_replaces_hint_dispatch(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V58")
        assert prompt_version_at_least("V59")
        assert v54_intra_chapter_action_repair_hint("writer") == v59_action_first_realization_hint("writer")
    finally:
        deactivate(token)


def test_v59_changes_narrative_order_without_adding_a_model_call(tmp_path):
    token = _activate(tmp_path)
    try:
        planner = v59_action_first_realization_hint("planner")
        writer = v59_action_first_realization_hint("writer")
        editor = v59_action_first_realization_hint("editor")
        validator = v59_action_first_realization_hint("validator")
        extractor = v59_action_first_realization_hint("extractor")
    finally:
        deactivate(token)

    assert "V59 先行动后解释" in planner
    assert "primary_action 和 character_turn 都必须是非空对象" in planner
    assert "cost_or_risk" in planner
    assert "现场压力、一次角色取舍、紧随其后的可见后果" in validator
    assert "最多一条必要信息" in writer
    assert "不触发 Writer 重写" in editor
    assert "不要把开场说明" in extractor
    assert "V58 结构化角色转折" not in writer
    assert "model call" not in writer.lower()


def test_v59_keeps_v58_direct_hint_available_for_archived_comparison(tmp_path):
    token = _activate(tmp_path)
    try:
        direct = v58_structured_character_turn_hint("writer")
    finally:
        deactivate(token)

    assert "V58 结构化角色转折" in direct
