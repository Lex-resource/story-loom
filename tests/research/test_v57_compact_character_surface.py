from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v57_compact_character_surface_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v57-compact-character-surface",
            prompt_version="V57",
            variant="ariadne-a43-v57-compact-character-surface",
            project_id="project",
            chapter_index=3,
            root_dir=tmp_path,
        )
    )


def test_v57_registers_after_v56(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V56")
        assert prompt_version_at_least("V57")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v57_compact_character_surface_hint(agent_type)
            assert "V57 精简角色叙事" in hint
    finally:
        deactivate(token)


def test_v57_replaces_accumulated_v54_to_v56_surface(tmp_path):
    token = _activate(tmp_path)
    try:
        writer_hint = v54_intra_chapter_action_repair_hint("writer")
        planner_hint = v54_intra_chapter_action_repair_hint("planner")
        expected_writer_hint = v57_compact_character_surface_hint("writer")
        expected_planner_hint = v57_compact_character_surface_hint("planner")
    finally:
        deactivate(token)

    assert writer_hint == expected_writer_hint
    assert planner_hint == expected_planner_hint
    assert "V56 角色驱动转折" not in writer_hint
    assert "V55 单一核心动作转折" not in writer_hint
    assert "连续读取、记录、确认" in writer_hint
