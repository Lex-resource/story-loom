from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v59_action_first_realization_hint,
    v60_external_consequence_hint,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v60-external-consequence",
            prompt_version="V60",
            variant="ariadne-a46-v60-external-consequence",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v60_dispatches_after_v59_without_changing_archived_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V59")
        assert prompt_version_at_least("V60")
        dispatched = v54_intra_chapter_action_repair_hint("writer")
        direct = v60_external_consequence_hint("writer")
        assert dispatched == direct
        assert "V60 界面外部后果" in direct
        assert "V60 界面外部后果" not in v59_action_first_realization_hint("writer")
    finally:
        deactivate(token)


def test_v60_requires_external_observable_state_for_each_agent(tmp_path):
    token = _activate(tmp_path)
    try:
        planner = v60_external_consequence_hint("planner")
        writer = v60_external_consequence_hint("writer")
        editor = v60_external_consequence_hint("editor")
        validator = v60_external_consequence_hint("validator")
        extractor = v60_external_consequence_hint("extractor")
    finally:
        deactivate(token)

    assert "不能只停留在屏幕" in planner
    assert "界面之外的可观察后果" in writer
    assert "优先局部压缩解释" in editor
    assert "只有屏幕/回执/提示音变化" in validator
    assert "界面外状态变化" in extractor
    assert "V59 先行动后解释" in writer
