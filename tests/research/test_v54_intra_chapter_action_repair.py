import json
from pathlib import Path
from types import SimpleNamespace

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
)
from agents.writing_schemas import PlannerChapterOutlineResponse
from services.continuity_contract import build_chapter_contract, contract_prompt
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate
from worker_support.generation_validator_policy import (
    requires_content_retry,
)
from research.prompt_versions.validator_policy import (
    build_v54_action_repair_contract,
    is_v54_action_surface_issue,
)


def _context(tmp_path):
    return ExperimentContext(
        run_id="v54-intra-chapter-action-repair",
        prompt_version="V54",
        variant="ariadne-a40-v54-intra-chapter-action-repair",
        project_id="project",
        chapter_index=4,
        root_dir=Path(tmp_path),
    )


def test_v54_registers_and_exposes_single_use_action_surface(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V53")
        assert prompt_version_at_least("V54")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v54_intra_chapter_action_repair_hint(agent_type)
            assert "V54 章节内动作账本" in hint
            if agent_type != "extractor":
                assert "unique_action_ledger" in hint
            else:
                assert "operation" in hint
            if agent_type == "writer":
                assert "待判定" in hint
    finally:
        deactivate(token)


def test_v54_contract_deduplicates_and_bounds_unique_actions(tmp_path):
    token = activate(_context(tmp_path))
    try:
        contract = build_chapter_contract(
            {
                "required_events": ["打开局部验证"],
                "unique_action_ledger": [
                    {"operation": "提交局部验证", "response": "权限不足", "change": "选项收缩"},
                    {"operation": "提交局部验证", "response": "重复项", "change": "不应重复"},
                    "进入字段确认界面",
                ],
                "new_stage_delta": ["从受限查询转入字段确认"],
            },
            {"completed_event_ledger": [{"event": "进入受限查询区"}]},
            enforce_authority=True,
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
    finally:
        deactivate(token)

    assert [item["operation"] for item in contract["unique_action_ledger"]] == [
        "提交局部验证",
        "进入字段确认界面",
    ]
    assert "unique_action_ledger" in rendered
    assert "previous_progress" in rendered


def test_outline_schema_accepts_unique_action_ledger():
    outline = PlannerChapterOutlineResponse(
        chapter_index=4,
        title="字段确认",
        summary="进入一次局部字段确认",
        emotional_arc="克制",
        unique_action_ledger=["提交局部验证"],
    )
    assert outline.unique_action_ledger == ["提交局部验证"]


def test_v54_local_action_issue_skips_writer_retry():
    token = activate(_context(Path(".")))
    issue = {
        "category": "logic",
        "error_type": "其他",
        "evidence": "他点下局部验证；随后再次提交当前片段",
        "conflicts_with": "同一局部验证操作只能执行一次",
        "fix_suggestion": "删除再次提交句，保留第一次响应",
    }
    try:
        assert is_v54_action_surface_issue(issue)
        assert not requires_content_retry({"passed": False, "hard_issues": [issue]})
        repair = build_v54_action_repair_contract({"hard_issues": [issue]})
        assert "只改动作重复或未知标签" in repair
        assert "再次提交" in repair
    finally:
        deactivate(token)


def test_v54_mixed_hard_conflict_still_retries():
    token = activate(_context(Path(".")))
    issue = {
        "category": "timeline",
        "error_type": "时间线矛盾",
        "description": "与已接受事实冲突",
        "evidence": "角色在尚未到达时已经进入现场",
        "conflicts_with": "已接受地点时间线",
    }
    try:
        assert not is_v54_action_surface_issue(issue)
        assert requires_content_retry({"passed": False, "hard_issues": [issue]})
    finally:
        deactivate(token)
