from pathlib import Path

from research.prompt_versions.hints import (
    v52_visible_consequence_chain_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v52-visible-consequence-chain",
        prompt_version="V52",
        variant="ariadne-a38-v52-visible-consequence-chain",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )


def test_v52_inherits_v51_and_reaches_all_writing_agents(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V51")
        assert prompt_version_at_least("V52")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v52_visible_consequence_chain_hint(agent_type)
            assert "V52 可见后果链" in hint
            assert "V51 角色选择落地" in hint
    finally:
        deactivate(token)


def test_v52_rejects_waiting_as_a_choice_but_keeps_hard_conflicts_blocking(tmp_path):
    token = activate(_context(tmp_path))
    try:
        planner_hint = v52_visible_consequence_chain_hint("planner")
        writer_hint = v52_visible_consequence_chain_hint("writer")
        validator_hint = v52_visible_consequence_chain_hint("validator")
    finally:
        deactivate(token)

    assert "dramatic_turn.choice 不得留空" in planner_hint
    assert "等待变化" in planner_hint
    assert "不算选择或后果" in writer_hint
    assert "列为 warning" in validator_hint
    assert "仍必须 block" in validator_hint
