import json

from research.prompt_versions.hints import (
    v46_dramatic_turn_hint,
)
from services.chapter_continuity import writer_execution_brief
from services.continuity_contract import build_chapter_contract, contract_prompt
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v46-dramatic-turn",
        prompt_version="V46",
        variant="ariadne-a32-v46-dramatic-turn",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )


def test_v46_projects_goal_pressure_choice_and_consequence(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V46")
        contract = build_chapter_contract(
            {
                "required_events": ["核对回执"],
                "character_goals": [
                    {
                        "character_name": "林默",
                        "goal": "确认回执是否指向下一条记录",
                        "conflict": "设备拒绝提供来源",
                        "state_change": "将调查目标转向后续记录",
                    }
                ],
                "emotional_arc": "谨慎期待转为克制的不安",
                "beats": [
                    {
                        "beat": "确认受限字段",
                        "purpose": "迫使林默改变查询策略",
                    },
                    {
                        "beat": "选择停止追问",
                        "purpose": "保留新的调查入口",
                    },
                ],
                "end_state": "调查目标转向后续记录",
            },
            {},
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
        dramatic = rendered["dramatic_turn"]
        assert dramatic["primary_character"] == "林默"
        assert dramatic["goal"] == "确认回执是否指向下一条记录"
        assert dramatic["pressure"] == "设备拒绝提供来源"
        assert dramatic["consequence"] == "将调查目标转向后续记录"
        assert len(dramatic["beats"]) == 2

        brief = json.loads(writer_execution_brief({}, contract))
        assert brief["chapter_execution"]["dramatic_turn"] == dramatic
    finally:
        deactivate(token)


def test_v46_hint_is_compact_and_soft_quality_is_not_a_hard_conflict(tmp_path):
    token = activate(_context(tmp_path))
    try:
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v46_dramatic_turn_hint(agent_type)
            assert "V46 戏剧转折" in hint
        validator_hint = v46_dramatic_turn_hint("validator")
        assert "只能作为 warning" in validator_hint
        assert "硬事实" in validator_hint
    finally:
        deactivate(token)
