"""Chapter rewrite state preparation."""
from typing import Optional

from services.pipeline_types import ChapterStatus, PipelineStep


def reset_chapter_for_rewrite(
    chapter,
    *,
    use_existing_outline: bool,
    custom_prompt: Optional[str] = None,
) -> None:
    """Reset a chapter to draft state for a rewrite."""
    chapter.status = ChapterStatus.DRAFT
    chapter.pipeline_step = (
        PipelineStep.WRITING if use_existing_outline else PipelineStep.OUTLINE
    )
    chapter.draft_content = ""
    chapter.edited_content = ""
    chapter.content = ""
    chapter.validator_result = None

    combined: list[str] = []
    if use_existing_outline and chapter.error:
        combined.append(f"上次未通过原因：\n{chapter.error}")
    if custom_prompt:
        combined.append(f"用户的特殊重写指令：\n{custom_prompt}")
    chapter.error = "\n\n".join(combined) if combined else None

    chapter.rewrite_count = (chapter.rewrite_count or 0) + 1
    if not use_existing_outline:
        chapter.outline = None
