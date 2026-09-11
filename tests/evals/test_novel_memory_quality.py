import json
from pathlib import Path

from services.novel_memory_recall import RECALL_BUDGETS, format_recall_context


def test_eval_cases_cover_the_memory_risk_surface():
    cases = json.loads(Path(__file__).with_name("novel_memory_cases.json").read_text(encoding="utf-8"))
    ids = {case["id"] for case in cases}
    assert {"character-state-transition", "foreshadowing-due", "branch-isolation", "manual-authority"} <= ids


def test_recall_context_respects_agent_character_budget():
    budget = RECALL_BUDGETS["writer"]
    context = format_recall_context([], [], [], [], budget.max_chars)
    assert len(context) <= budget.max_chars


def test_branch_case_requires_explicit_scope_dimensions():
    cases = json.loads(Path(__file__).with_name("novel_memory_cases.json").read_text(encoding="utf-8"))
    branch_case = next(case for case in cases if case["id"] == "branch-isolation")
    assert set(branch_case["expected"]) == {"branch_id", "storyline_id"}
