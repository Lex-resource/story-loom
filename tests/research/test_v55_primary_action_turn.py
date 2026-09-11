import json
from pathlib import Path

from research.prompt_versions.hints import (
    v55_primary_action_turn_hint,
)
from services.continuity_contract import build_chapter_contract, contract_prompt, prompt_outline_for_agent
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path):
    return activate(
        ExperimentContext(
            run_id="v55-primary-action-turn",
            prompt_version="V55",
            variant="ariadne-a41-v55-primary-action-turn",
            project_id="project",
            chapter_index=3,
            root_dir=Path(tmp_path),
        )
    )


def test_v55_registers_after_v54_and_replaces_primary_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V54")
        assert prompt_version_at_least("V55")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v55_primary_action_turn_hint(agent_type)
            assert "V55 单一核心动作转折" in hint
            assert "action" in hint
    finally:
        deactivate(token)


def test_v55_normalizes_and_renders_primary_action(tmp_path):
    token = _activate(tmp_path)
    try:
        contract = build_chapter_contract(
            {
                "required_events": ["查看一次历史回执"],
                "primary_action": {
                    "operation": "查看历史回执",
                    "result": "只返回残缺字段",
                    "next_choice": "放弃继续查询并进入内部通道",
                    "risk": "失去门外复查机会",
                    "stage_delta": "调查转入塔内",
                },
                "new_stage_delta": ["进入塔内受限查询区"],
            },
            {"completed_event_ledger": [{"event": "跨入白塔"}]},
            enforce_authority=True,
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
    finally:
        deactivate(token)

    assert contract["primary_action"] == {
        "action": "查看历史回执",
        "response": "只返回残缺字段",
        "decision": "放弃继续查询并进入内部通道",
        "cost_or_risk": "失去门外复查机会",
        "new_stage": "调查转入塔内",
    }
    assert rendered["primary_action"]["decision"] == "放弃继续查询并进入内部通道"
    assert "primary_action" in prompt_outline_for_agent(
        {"primary_action": contract["primary_action"]}, agent_type="writer"
    )
