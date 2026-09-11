from pathlib import Path

from research.prompt_versions.hints import (
    v51_character_agency_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v51-character-agency",
        prompt_version="V51",
        variant="ariadne-a37-v51-character-agency",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )


def test_v51_version_and_shared_prompt_surface(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V50")
        assert prompt_version_at_least("V51")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v51_character_agency_hint(agent_type)
            assert "V51 角色选择落地" in hint
            assert "V50 最小证据修复" in hint
    finally:
        deactivate(token)


def test_v51_keeps_character_quality_soft_and_hard_conflicts_hard(tmp_path):
    token = activate(_context(tmp_path))
    try:
        validator_hint = v51_character_agency_hint("validator")
    finally:
        deactivate(token)

    assert "不能单独触发 Writer 重写" in validator_hint
    assert "仍必须 block" in validator_hint

