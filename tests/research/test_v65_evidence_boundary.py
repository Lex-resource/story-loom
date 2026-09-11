from pathlib import Path

from research.prompt_versions.hints import (
    v65_evidence_boundary_hint,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate
from worker_support.generation_validator_policy import (
    requires_content_retry,
)
from research.prompt_versions.validator_policy import (
    build_v65_evidence_boundary_repair_contract,
    is_v65_evidence_boundary_issue,
)


def _context(tmp_path):
    return ExperimentContext(
        run_id="v65-evidence-boundary",
        prompt_version="V65",
        variant="ariadne-a51-v65-evidence-boundary",
        project_id="project",
        chapter_index=5,
        root_dir=Path(tmp_path),
    )


def test_v65_prompt_surface_is_shared_by_all_writing_agents(tmp_path):
    token = activate(_context(tmp_path))
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v65_evidence_boundary_hint(agent_type)
            assert "V65 证据边界闸门" in hint
        assert "观察" in v65_evidence_boundary_hint("writer")
        assert "evidence_boundary/local_repair" in v65_evidence_boundary_hint("validator")
    finally:
        deactivate(token)


def test_v65_classifies_device_and_trace_overclaims_as_local_repairs(tmp_path):
    issue = {
        "category": "item_state",
        "error_type": "物品状态矛盾",
        "description": "设备提示不能证明对象真实存在或已经转移。",
        "evidence": "对象已经被带走，应该沿检修段追查。",
        "conflicts_with": "屏幕内容仍只是观察到的界面信息，真实转移尚待核查。",
        "fix_suggestion": "改为：显示内容指向该可能性，但是否真实转移仍需核查。",
    }
    token = activate(_context(tmp_path))
    try:
        assert is_v65_evidence_boundary_issue(issue)
        assert not requires_content_retry({"passed": False, "hard_issues": [issue]})
    finally:
        deactivate(token)


def test_v65_keeps_real_accepted_fact_conflicts_retryable(tmp_path):
    issue = {
        "category": "item_state",
        "error_type": "物品状态矛盾",
        "description": "正文写成物品已经转移，与已接受事实冲突。",
        "evidence": "物品已经被带走。",
        "conflicts_with": "与已接受事实冲突：物品仍在林默手中。",
    }
    token = activate(_context(tmp_path))
    try:
        assert not is_v65_evidence_boundary_issue(issue)
        assert requires_content_retry({"passed": False, "hard_issues": [issue]})
    finally:
        deactivate(token)


def test_v65_repair_contract_preserves_evidence_and_boundaries(tmp_path):
    result = {
        "hard_issues": [
            {
                "evidence": "对象已经被带走。",
                "conflicts_with": "设备显示不等于真实转移。",
                "fix_suggestion": "改为：屏幕显示为对象已转移，但仍需核查。",
            }
        ]
    }
    token = activate(_context(tmp_path))
    try:
        contract = build_v65_evidence_boundary_repair_contract(result)
    finally:
        deactivate(token)
    assert "对象已经被带走" in contract
    assert "屏幕显示为对象已转移" in contract
    assert "不得新增人物" in contract
