from agents.constants import AGENT_EDITOR, AGENT_EXTRACTOR
from agents.writing_schemas import EditorResponse
from services.novel_constants import EDITOR_DECISION_REWRITE
from services.knowledge_patch_models import KnowledgePatchSet
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, PipelineStep
from services.editor_policy import min_score_from_evaluations, resolve_editor_decision


class ChapterReviewError(ValueError):
    pass


async def apply_editor_review_json(db, chapter, corrected_json: dict) -> dict:
    try:
        validated = EditorResponse.model_validate(corrected_json)
    except Exception as error:
        raise ChapterReviewError(f"JSON 验证失败: {error}") from error

    eval_data = validated.evaluations.model_dump()
    min_score = min_score_from_evaluations(eval_data)
    decision = resolve_editor_decision(
        min_score,
        chapter.rewrite_count or 0,
        validated.model_dump(),
    )

    chapter.edited_content = validated.edited_content
    chapter.evaluations = eval_data
    chapter.editor_decision = decision

    if decision == EDITOR_DECISION_REWRITE:
        chapter.status = ChapterStatus.DRAFT
        set_chapter_pipeline_step(chapter, PipelineStep.WRITING)
        chapter.error = validated.rewrite_reason or ""
    else:
        chapter.status = ChapterStatus.VALIDATED
        set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)
        chapter.error = None

    await db.commit()
    return {"status": chapter.status, "message": "已成功保存编辑器数据。"}


async def apply_extractor_review_json(db, novel, chapter, corrected_json: dict) -> dict:
    try:
        validated = KnowledgePatchSet.model_validate(corrected_json)
    except Exception as error:
        raise ChapterReviewError(f"JSON 验证失败: {error}") from error

    from services.knowledge_merger import apply_extractor_updates

    await apply_extractor_updates(db, novel, chapter, validated.model_dump(by_alias=True))
    if chapter.status == ChapterStatus.PENDING_REVIEW:
        await db.commit()
        return {"status": ChapterStatus.PENDING_REVIEW, "message": "设定变更仍需人工复核。"}
    chapter.error = None
    await db.commit()
    return {"status": ChapterStatus.PUBLISHED, "message": "已成功保存并应用提取器设定更新。"}


async def apply_review_json(db, novel, chapter, step: str, corrected_json: dict) -> dict:
    if step == AGENT_EDITOR:
        return await apply_editor_review_json(db, chapter, corrected_json)
    if step == AGENT_EXTRACTOR:
        return await apply_extractor_review_json(db, novel, chapter, corrected_json)
    raise ChapterReviewError("Invalid step name")
