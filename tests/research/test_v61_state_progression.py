from pathlib import Path

from research.prompt_versions.hints import (
    v60_external_consequence_hint,
    v61_state_progression_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_v61_is_a_distinct_successor_to_v60(tmp_path):
    token = activate(
        ExperimentContext(
            run_id="v61-state-progression",
            prompt_version="V61",
            variant="ariadne-a47-v61-state-progression",
            project_id="project",
            chapter_index=2,
            root_dir=Path(tmp_path),
        )
    )
    try:
        assert prompt_version_at_least("V60")
        assert prompt_version_at_least("V61")
        hint = v61_state_progression_hint("writer")
        assert "V61 状态演进收束" in hint
        assert "设备/回执限制只解释一次" in hint
        assert "V61 状态演进收束" not in v60_external_consequence_hint("writer")
    finally:
        deactivate(token)


def test_v61_applies_to_all_generation_agents(tmp_path):
    token = activate(
        ExperimentContext(
            run_id="v61-all-agents",
            prompt_version="V61",
            variant="ariadne-a47-v61-state-progression",
            project_id="project",
            chapter_index=2,
            root_dir=Path(tmp_path),
        )
    )
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            assert "V61 状态演进收束" in v61_state_progression_hint(agent_type)
    finally:
        deactivate(token)
