from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v65_evidence_boundary_hint,
    v66_compact_character_texture_hint,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path: Path, version: str):
    return ExperimentContext(
        run_id=f"{version.lower()}-compact-character-texture",
        prompt_version=version,
        variant=f"ariadne-a52-{version.lower()}-compact-character-texture",
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )


def test_v66_uses_compact_role_specific_surface(tmp_path):
    token = activate(_context(tmp_path, "V66"))
    try:
        hints = {
            role: v54_intra_chapter_action_repair_hint(role)
            for role in ("planner", "writer", "editor", "validator", "extractor")
        }
    finally:
        deactivate(token)

    assert all("V66" in hint for hint in hints.values())
    assert "具体选择" in hints["writer"]
    assert "可见回应" in hints["writer"]
    assert "只解释一次" in hints["writer"]
    assert "evidence_boundary/local_repair" in hints["validator"]
    assert "V65 证据边界闸门" not in hints["writer"]


def test_v66_does_not_change_v65_dispatch(tmp_path):
    token = activate(_context(tmp_path, "V65"))
    try:
        dispatched = v54_intra_chapter_action_repair_hint("writer")
        direct = v65_evidence_boundary_hint("writer")
    finally:
        deactivate(token)

    assert dispatched == direct
    assert "V65 证据边界闸门" in dispatched
    assert "V66 单章叙事执行面" not in dispatched
