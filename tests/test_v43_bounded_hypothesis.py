from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate
from agents.prompt_hints import v43_bounded_hypothesis_progression_hint
from worker_support.generation_validator_policy import (
    is_bounded_hypothesis_issue,
    requires_content_retry,
)


def _context(tmp_path, variant="ariadne-a28-v43-bounded-hypothesis"):
    return ExperimentContext(
        run_id="a28-test",
        prompt_version="V43",
        variant=variant,
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )


def test_v43_is_ordered_after_v42_and_reaches_all_agent_hints(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V42")
        assert prompt_version_at_least("V43")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v43_bounded_hypothesis_progression_hint(agent_type)
            assert "V43 受限假设推进与最小叙事增量" in hint
    finally:
        deactivate(token)


def test_a28_keeps_bounded_hypothesis_on_local_repair_path(tmp_path):
    issue = {
        "severity": "block",
        "category": "consistency",
        "error_type": "身份表述越界",
        "description": "正文已把候选线索写成事实，应改为明确的假设或待核实表达",
    }
    token = activate(_context(tmp_path))
    try:
        assert is_bounded_hypothesis_issue(issue)
        assert not requires_content_retry({"passed": False, "hard_issues": [issue]})
    finally:
        deactivate(token)


def test_a28_still_retries_real_accepted_fact_conflicts(tmp_path):
    issue = {
        "severity": "block",
        "category": "timeline",
        "error_type": "时间线矛盾",
        "description": "正文与已接受事实冲突，且没有观察到中间转变",
    }
    token = activate(_context(tmp_path))
    try:
        assert not is_bounded_hypothesis_issue(issue)
        assert requires_content_retry({"passed": False, "hard_issues": [issue]})
    finally:
        deactivate(token)


def test_bounded_hypothesis_policy_applies_to_production(tmp_path):
    """有界假设的局部修复路径现在是生产行为，不再只属于 A28 实验。

    生产已冻结在 A28/V43（见 docs/research/novel-memory-continuity/PRODUCTION.md）。
    该策略原先要求 variant 以 `ariadne-a28` 开头才生效，导致普通生产运行拿不到
    PRODUCTION.md 记录的零内容重试行为。现在它无条件生效，因此与 variant 无关。
    """
    issue = {
        "severity": "block",
        "category": "consistency",
        "description": "候选线索应保持为假设，不得确认身份",
    }
    # 无 ExperimentContext（普通生产运行）
    assert is_bounded_hypothesis_issue(issue)

    # 任意 variant 下结论相同——判据已不再看 variant
    for variant in ("production-v43", "ariadne-a28-v43-bounded-hypothesis"):
        token = activate(_context(tmp_path, variant=variant))
        try:
            assert is_bounded_hypothesis_issue(issue)
        finally:
            deactivate(token)
