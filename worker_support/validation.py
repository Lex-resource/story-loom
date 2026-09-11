import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_VALIDATOR
from agents.pipeline_context import PipelineContext
from services.editor_policy import min_score_from_evaluations, resolve_editor_decision
from services.validation_constants import (
    VALIDATION_MODE_QUICK_POST_EDIT,
    VALIDATION_PHASE_QUICK,
    VALIDATION_PHASE_LLM,
    ISSUE_SEVERITY_BLOCK,
    ISSUE_SEVERITY_WARNING,
    VALIDATOR_DEFAULT_CATEGORY,
    is_fact_conflict_issue,
)
from services.validator import validate_chapter


STORY_REVIEW_CATEGORIES = {"style", "pacing", "character", "character_portrayal", "writing_quality"}
BLOCKING_SEVERITIES = {"block", "high", "critical", "error"}
WARNING_SEVERITIES = {"warning", "medium", "warn"}


async def run_quick_validation(
    db: AsyncSession, project_id: uuid.UUID, chapter_index: int, title: str, content: str,
    target_word_count: int, previous_ending: str, mem_context: dict
) -> dict:
    """Quick regex/blacklist validation (no LLM call).

    db / project_id / chapter_index / mem_context are accepted for signature
    symmetry with run_comprehensive_validation but not used here.
    """
    quick_res = validate_chapter(
        content,
        title,
        target_word_count,
        previous_ending
    )

    errors = quick_res.get("errors", [])[:]

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": quick_res.get("warnings", [])[:],
        "infos": [],
        "word_count": quick_res.get("word_count", len(content)),
        "repeat_rate": quick_res.get("repeat_rate", 0.0),
        "cleaned_title": quick_res.get("cleaned_title", title),
        "cleaned_content": quick_res.get("cleaned_content", content),
        "validation_mode": VALIDATION_MODE_QUICK_POST_EDIT,
    }


async def run_comprehensive_validation(
    db: AsyncSession,
    project_id: uuid.UUID,
    chapter_index: int,
    title: str,
    content: str,
    target_word_count: int,
    previous_ending: str,
    mem_context: dict,
    validator_agent,
    on_validator_chunk=None,
) -> dict:
    project_id_str = str(project_id)

    async def emit_chunk(phase: str, text: str):
        if on_validator_chunk:
            await on_validator_chunk(phase, text)

    await emit_chunk(VALIDATION_PHASE_QUICK, "▶ 快速语法与词汇合规性检测启动…\n")

    # 1. Quick regex/blacklist validation
    quick_res = validate_chapter(
        content,
        title,
        target_word_count,
        previous_ending
    )

    quick_lines = []
    for err in quick_res.get("errors", []):
        quick_lines.append(f"[拦截] {err}")
    for warn in quick_res.get("warnings", []):
        quick_lines.append(f"[警告] {warn}")
    if quick_lines:
        await emit_chunk(VALIDATION_PHASE_QUICK, "\n".join(quick_lines) + "\n")
    else:
        await emit_chunk(VALIDATION_PHASE_QUICK, "✓ 快速检测未发现硬性违规\n")

    await emit_chunk(VALIDATION_PHASE_LLM, "▶ LLM 深度设定逻辑审计启动…\n")

    # 2. LLM logical contradiction validation
    async def llm_cb(source: str, chunk: str):
        if source == "reasoning":
            pass  # Or handle reasoning
        else:
            await emit_chunk(VALIDATION_PHASE_LLM, chunk)

    validation_context = PipelineContext.from_memory(project_id_str, chapter_index, {**mem_context, "previous_ending": previous_ending})
    llm_output = await validator_agent.run(
        validation_context,
        {"title": title, "content": content, "on_chunk": llm_cb},
    )
    llm_res = llm_output.payload
    await validator_agent.agent.record_usage(db, project_id, chapter_index, AGENT_VALIDATOR)

    # Merge errors, warnings, and infos
    errors = quick_res.get("errors", [])[:]
    warnings = quick_res.get("warnings", [])[:]
    infos = []
    story_issues = []
    hard_issues = []

    for issue in llm_res.get("issues", []):
        desc = f"[{issue.get('category', VALIDATOR_DEFAULT_CATEGORY)}] {issue.get('description', '')} (建议：{issue.get('fix_suggestion', '')})"
        sev = issue.get("severity", ISSUE_SEVERITY_BLOCK).lower()
        category = str(issue.get("category", VALIDATOR_DEFAULT_CATEGORY)).lower()
        fact_conflict = is_fact_conflict_issue(issue)
        issue_payload = {**issue, "message": desc}
        # A severe writing_quality finding must be able to force a rewrite even
        # when plot/setting are fine — otherwise "设定全对但平庸无聊" always passes.
        # style/pacing/character stay observe-only (story_issues); only
        # writing_quality at blocking severity falls through to the errors gate.
        quality_gate_override = (
            category == "writing_quality" and sev in BLOCKING_SEVERITIES
        )
        # style/pacing/character 一律只作观察项（story_issues），不进 errors 阻断；只有
        # writing_quality 到阻断级才掉下去。这条分流原先加了 `novel_format == 长篇` 的前提，
        # 于是短篇和一切自定义工作流都拿不到 —— 短篇表面明明宣布「节奏、密度、文风、爽点
        # 一律 warning，不得单独触发重写」（services/short_form_surfaces.py:59-66），实际却比
        # 长篇更严：pacing 判 block 会直接进 errors。分流本身与工作流无关，去掉那个前提。
        if fact_conflict:
            issue_payload["severity"] = ISSUE_SEVERITY_BLOCK
            errors.append(desc)
            hard_issues.append(issue_payload)
        elif category in STORY_REVIEW_CATEGORIES and not quality_gate_override:
            story_issues.append(issue_payload)
        elif sev in BLOCKING_SEVERITIES:
            errors.append(desc)
            hard_issues.append(issue_payload)
        elif sev in WARNING_SEVERITIES:
            warnings.append(desc)
            hard_issues.append(issue_payload)
        else:
            infos.append(desc)
            hard_issues.append(issue_payload)

    passed = len(errors) == 0

    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "word_count": quick_res.get("word_count", len(content)),
        "repeat_rate": quick_res.get("repeat_rate", 0.0),
        "cleaned_title": quick_res.get("cleaned_title", title),
        "cleaned_content": quick_res.get("cleaned_content", content),
        "hard_issues": hard_issues,
        "story_issues": story_issues,
    }



