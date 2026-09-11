from pathlib import Path

from research.prompt_versions.hints import (
    v49_observation_language_hint,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate
from research.prompt_versions.validator_policy import (
    is_v49_observation_language_issue,
)


def test_v49_routes_observation_to_history_upgrade_to_local_repair(tmp_path):
    context = ExperimentContext(
        run_id="v49-observation-language",
        prompt_version="V49",
        variant="ariadne-a35-v49-observation-language",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )
    issue = {
        "category": "logic",
        "error_type": "因果颠倒",
        "description": "将界面上残缺的显示升级为真实历史，并推断原始请求导致设备只留下残片。",
        "evidence": "谁曾提交过原始请求？",
    }
    token = activate(context)
    try:
        assert is_v49_observation_language_issue(issue)
    finally:
        deactivate(token)


def test_v49_does_not_downgrade_a_real_hard_boundary_conflict(tmp_path):
    context = ExperimentContext(
        run_id="v49-hard-boundary",
        prompt_version="V49",
        variant="ariadne-a35-v49-observation-language",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )
    issue = {
        "category": "consistency",
        "error_type": "时间线矛盾",
        "description": "界面显示与已接受事实冲突，且核心事件缺失。",
    }
    token = activate(context)
    try:
        assert not is_v49_observation_language_issue(issue)
    finally:
        deactivate(token)


def test_v49_prompt_surface_is_shared_by_all_writing_agents(tmp_path):
    context = ExperimentContext(
        run_id="v49-prompt-surface",
        prompt_version="V49",
        variant="ariadne-a35-v49-observation-language",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )
    token = activate(context)
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            assert "V49 证据语言边界" in v49_observation_language_hint(agent_type)
    finally:
        deactivate(token)
