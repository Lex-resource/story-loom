from services.novel_constants import (
    EDITOR_DECISION_PROCEED,
    EDITOR_DECISION_REWRITE,
    EDITOR_DEFAULT_SCORE,
    EDITOR_MAX_REWRITES_FALLBACK,
    EDITOR_MIN_PASS_SCORE,
)


def resolve_editor_decision(min_score: int, rewrite_count: int, editor_result: dict) -> str:
    rewrite_reason = editor_result.get("rewrite_reason")
    edited_content = editor_result.get("edited_content", "").strip()
    if rewrite_reason and not edited_content:
        return EDITOR_DECISION_REWRITE
    if min_score < EDITOR_MIN_PASS_SCORE and rewrite_count < EDITOR_MAX_REWRITES_FALLBACK:
        return EDITOR_DECISION_REWRITE
    return EDITOR_DECISION_PROCEED


def min_score_from_evaluations(evaluations: dict) -> int:
    if not isinstance(evaluations, dict):
        return EDITOR_DEFAULT_SCORE
    scores = []
    for value in evaluations.values():
        if isinstance(value, dict) and "score" in value:
            try:
                scores.append(int(value["score"]) * 10)
            except (TypeError, ValueError):
                continue
    return min(scores) if scores else EDITOR_DEFAULT_SCORE
