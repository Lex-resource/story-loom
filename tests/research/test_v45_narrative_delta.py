from research.prompt_versions.hints import (
    v45_narrative_delta_hint,
)
from services.context_compaction import context_budget_for
from services.continuity_contract import prompt_outline_for_agent
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v45-narrative-delta",
        prompt_version="V45",
        variant="ariadne-a31-v45-narrative-delta",
        project_id="project",
        chapter_index=4,
        root_dir=tmp_path,
    )


def test_v45_preserves_v44_surface_and_adds_role_specific_delta_rules(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V44")
        assert prompt_version_at_least("V45")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v45_narrative_delta_hint(agent_type)
            assert "V44 输入面压缩与上下文所有权" in hint
            assert "V45 单次证据与叙事增量" in hint
        assert "物品账本未登记时禁止新增纸张" in v45_narrative_delta_hint("writer")
    finally:
        deactivate(token)


def test_v45_trims_validator_outline_projection_and_review_budgets(tmp_path):
    token = activate(_context(tmp_path))
    try:
        projected = prompt_outline_for_agent(
            {
                "chapter_index": 4,
                "title": "第四章",
                "summary": "推进调查",
                "key_events": ["旧字段"],
                "required_events": ["完成一次核验"],
                "state_changes": ["旧状态投影"],
                "end_state": "位置改变",
                "forbidden_deviations": ["不要确认未知身份"],
                "related_foreshadowing": ["见证者线索"],
                "continuity_contract": {"audit": "drop"},
            },
            agent_type="validator",
        )
        assert projected == {
            "chapter_index": 4,
            "title": "第四章",
            "required_events": ["完成一次核验"],
            "end_state": "位置改变",
            "forbidden_deviations": ["不要确认未知身份"],
            "related_foreshadowing": ["见证者线索"],
        }
        assert context_budget_for("validator").contract_chars < 2600
        assert context_budget_for("extractor").memory_chars < 2200
    finally:
        deactivate(token)
