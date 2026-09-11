from pathlib import Path

from research.prompt_versions.hints import (
    v50_minimal_observation_patch_hint,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate
from research.prompt_versions.validator_policy import (
    build_v50_observation_repair_contract,
    is_v50_minimal_observation_issue,
)


def _context(tmp_path):
    return ExperimentContext(
        run_id="v50-minimal-observation",
        prompt_version="V50",
        variant="ariadne-a36-v50-minimal-observation-patch",
        project_id="project",
        chapter_index=2,
        root_dir=Path(tmp_path),
    )


def test_v50_prompt_surface_is_shared_by_all_writing_agents(tmp_path):
    token = activate(_context(tmp_path))
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v50_minimal_observation_patch_hint(agent_type)
            assert "V50 最小证据修复" in hint
        assert "只替换" in v50_minimal_observation_patch_hint("editor")
    finally:
        deactivate(token)


def test_v50_accepts_only_the_v49_observation_language_class(tmp_path):
    issue = {
        "category": "logic",
        "error_type": "因果颠倒",
        "description": "将界面显示升级为真实历史，并推断发送者和原始请求导致当前结果。",
        "evidence": "谁曾提交过原始请求？",
        "conflicts_with": "发送者和原始请求仍未知",
        "fix_suggestion": "改为：是否对应某个原始请求？目前仍无法确认。",
    }
    hard_issue = {
        **issue,
        "description": "与已接受事实冲突：界面显示的地点和已发布地点不一致。",
    }
    token = activate(_context(tmp_path))
    try:
        assert is_v50_minimal_observation_issue(issue)
        assert not is_v50_minimal_observation_issue(hard_issue)
    finally:
        deactivate(token)


def test_v50_contract_preserves_validator_evidence_and_replacement(tmp_path):
    result = {
        "hard_issues": [
            {
                "evidence": "它只承认已经存在的回执。",
                "conflicts_with": "只能确认界面显示了标注，不确认真实历史。",
                "fix_suggestion": "改为：它只显示一段标注为历史回执的残缺内容。",
            }
        ]
    }
    token = activate(_context(tmp_path))
    try:
        contract = build_v50_observation_repair_contract(result)
    finally:
        deactivate(token)
    assert "它只承认已经存在的回执" in contract
    assert "它只显示一段标注为历史回执的残缺内容" in contract
    assert "除目标句外" in contract
