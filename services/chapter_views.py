def validator_auto_force_saved(chapter) -> bool:
    return (
        bool(chapter.validator_result.get("auto_force_saved"))
        if isinstance(chapter.validator_result, dict)
        else False
    )


def chapter_list_item(chapter) -> dict:
    return {
        "chapter_index": chapter.chapter_index,
        "title": chapter.title,
        "status": chapter.status,
        "pipeline_step": chapter.pipeline_step,
        "word_count": chapter.word_count,
        "force_corrected": chapter.force_corrected,
        "review_flags": chapter.review_flags,
        "editor_decision": chapter.editor_decision,
        "validator_auto_force_saved": validator_auto_force_saved(chapter),
    }


def chapter_detail(chapter) -> dict:
    return {
        "chapter_index": chapter.chapter_index,
        "title": chapter.title,
        "content": chapter.content,
        "draft_content": chapter.draft_content,
        "edited_content": chapter.edited_content,
        "status": chapter.status,
        "pipeline_step": chapter.pipeline_step,
        "word_count": chapter.word_count,
        "outline": chapter.outline,
        "editor_decision": chapter.editor_decision,
        "rewrite_count": chapter.rewrite_count,
        "force_corrected": chapter.force_corrected,
        "error": chapter.error,
        "validator_result": chapter.validator_result,
        "validator_auto_force_saved": validator_auto_force_saved(chapter),
        "review_flags": chapter.review_flags,
        "evaluations": chapter.evaluations,
    }
