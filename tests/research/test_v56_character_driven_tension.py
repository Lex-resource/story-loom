import json
from pathlib import Path

from research.prompt_versions.hints import (
    v56_character_driven_tension_hint,
)
from agents.writing_schemas import PlannerChapterOutlineResponse
from services.continuity_contract import build_chapter_contract, contract_prompt, prompt_outline_for_agent
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _activate(tmp_path: Path):
    return activate(
        ExperimentContext(
            run_id="v56-character-driven-tension",
            prompt_version="V56",
            variant="ariadne-a42-v56-character-driven-tension",
            project_id="project",
            chapter_index=3,
            root_dir=tmp_path,
        )
    )


def test_v56_registers_after_v55_and_replaces_shared_hint(tmp_path):
    token = _activate(tmp_path)
    try:
        assert prompt_version_at_least("V55")
        assert prompt_version_at_least("V56")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v56_character_driven_tension_hint(agent_type)
            assert "V56 角色驱动转折" in hint
            assert "character_turn" in hint
    finally:
        deactivate(token)


def test_v56_normalizes_and_renders_grounded_character_turn(tmp_path):
    token = _activate(tmp_path)
    try:
        contract = build_chapter_contract(
            {
                "required_events": ["越过门侧边界"],
                "primary_action": {
                    "action": "沿亮线移动设备",
                    "response": "暗面显出浅层落脚处",
                    "decision": "只进入一步",
                    "cost_or_risk": "退路被部分遮断",
                    "new_stage": "进入浅层入口",
                },
                "character_turn": {
                    "character_name": "林默",
                    "immediate_goal": "确认是否存在可继续调查的路径",
                    "conflict": "亮线正在收缩且入口性质未知",
                    "basis": "上一章已停止追问发送者并改查门侧结构",
                    "decision": "冒险进入一步",
                    "cost": "失去门外的完整安全距离",
                    "consequence": "调查从门侧转向向下路径",
                },
            },
            {"completed_event_ledger": [{"event": "停在门侧亮线前"}]},
            enforce_authority=True,
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
        writer_outline = prompt_outline_for_agent(
            {"character_turn": contract["character_turn"]}, agent_type="writer"
        )
    finally:
        deactivate(token)

    assert contract["character_turn"] == {
        "actor": "林默",
        "goal": "确认是否存在可继续调查的路径",
        "pressure": "亮线正在收缩且入口性质未知",
        "choice_basis": "上一章已停止追问发送者并改查门侧结构",
        "choice": "冒险进入一步",
        "personal_cost": "失去门外的完整安全距离",
        "state_change": "调查从门侧转向向下路径",
    }
    assert rendered["character_turn"]["choice_basis"].startswith("上一章")
    assert writer_outline["character_turn"]["personal_cost"] == "失去门外的完整安全距离"


def test_v56_outline_schema_accepts_character_turn():
    outline = PlannerChapterOutlineResponse(
        chapter_index=2,
        title="第2章",
        summary="推进",
        key_events=["选择"],
        emotional_arc="克制到决断",
        character_turn={"actor": "林默", "choice": "进入"},
    )
    assert outline.character_turn["choice"] == "进入"
