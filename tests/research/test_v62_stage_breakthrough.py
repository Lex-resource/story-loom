from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v61_state_progression_hint,
    v62_stage_breakthrough_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v62-stage-breakthrough",
            prompt_version="V62",
            variant="ariadne-a48-v62-stage-breakthrough",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v62_dispatches_after_v61_without_mutating_archived_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V61")
        assert prompt_version_at_least("V62")
        dispatched = v54_intra_chapter_action_repair_hint("writer")
        direct = v62_stage_breakthrough_hint("writer")
        assert dispatched == direct
        assert "V62 阶段突破" in direct
        assert "V62 阶段突破" not in v61_state_progression_hint("writer")
    finally:
        deactivate(token)


def test_v62_requires_an_information_or_cost_delta_for_each_agent(tmp_path):
    token = _activate(tmp_path)
    try:
        planner = v62_stage_breakthrough_hint("planner")
        writer = v62_stage_breakthrough_hint("writer")
        editor = v62_stage_breakthrough_hint("editor")
        validator = v62_stage_breakthrough_hint("validator")
        extractor = v62_stage_breakthrough_hint("extractor")
    finally:
        deactivate(token)

    assert "信息性结果或真实代价" in planner
    assert "不算阶段突破" in writer
    assert "压缩循环" in editor
    assert "终态是否包含信息性结果或真实代价" in validator
    assert "更具体的待验证条件" in extractor
