import json
from pathlib import Path

from research.prompt_versions.hints import (
    v54_intra_chapter_action_repair_hint,
    v58_structured_character_turn_hint,
)
from services.continuity_contract import build_chapter_contract, contract_prompt
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v58-structured-character-turn",
            prompt_version="V58",
            variant="ariadne-a44-v58-structured-character-turn",
            project_id="project",
            chapter_index=2,
            root_dir=tmp_path,
        )
    )


def test_v58_requires_structured_turn_without_old_hint_chain(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V58")
        hint = v54_intra_chapter_action_repair_hint("planner")
        direct = v58_structured_character_turn_hint("planner")
    finally:
        deactivate(token)

    assert hint == direct
    assert "必须输出非空 primary_action 和 character_turn" in hint
    assert "V57 精简角色叙事" not in hint
    assert "V56 角色驱动转折" not in hint


def test_v58_derives_missing_turn_from_existing_goal_and_action(tmp_path):
    token = _activate(tmp_path)
    try:
        contract = build_chapter_contract(
            {
                "character_goals": [{
                    "character_name": "林默",
                    "goal": "找到可验证的回执线索",
                    "conflict": "设备拒绝直接回答",
                    "state_change": "转向研究历史回执",
                }],
                "primary_action": {
                    "action": "请求历史回执",
                    "response": "设备返回残缺记录",
                    "decision": "放弃继续追问发送者",
                    "cost_or_risk": "继续停留会增加暴露风险",
                    "new_stage": "调查转向历史回执",
                },
            },
            {},
            enforce_authority=True,
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
    finally:
        deactivate(token)

    assert contract["character_turn"] == {
        "actor": "林默",
        "goal": "找到可验证的回执线索",
        "pressure": "设备拒绝直接回答",
        "choice_basis": "设备返回残缺记录",
        "choice": "放弃继续追问发送者",
        "personal_cost": "继续停留会增加暴露风险",
        "state_change": "调查转向历史回执",
    }
    assert rendered["character_turn"]["personal_cost"] == "继续停留会增加暴露风险"
