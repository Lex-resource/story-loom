"""Database-owned prompt template requirements.

Prompt contents are seeded by Alembic and edited through the system
configuration API. Runtime code must never read a second prompt store from
the repository, so this module only exposes the required-key registry and a
startup health check.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import (
    AGENT_WRITER,
    NOVEL_FORMAT_LONG_WEBNOVEL,
    NOVEL_FORMAT_ZHIHU_SHORT,
    PROMPT_CHARACTER_GENERATE_CARDS,
    PROMPT_COMMUNITY_SUMMARIZER,
    PROMPT_EXTRACT_CHARACTER_CARDS,
    PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
    PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE,
    PROMPT_SCENE_BLOCK_CONSOLIDATION,
    PROMPT_VALIDATOR_EXTRACT_ENTITIES,
    PROMPT_VALIDATOR_REVIEW_FULL_STORY,
)
from models.novel import PromptTemplate


REQUIRED_PROMPT_TEMPLATES: tuple[tuple[str, str], ...] = (
    (PROMPT_CHARACTER_GENERATE_CARDS, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_CHARACTER_GENERATE_CARDS, NOVEL_FORMAT_LONG_WEBNOVEL),
    (PROMPT_EXTRACT_CHARACTER_CARDS, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_EXTRACT_CHARACTER_CARDS, NOVEL_FORMAT_LONG_WEBNOVEL),
    (PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE, NOVEL_FORMAT_ZHIHU_SHORT),
    (AGENT_WRITER, NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_review", NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_force_revise", NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_destyle", NOVEL_FORMAT_ZHIHU_SHORT),
    ("validator_validate_content", NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_VALIDATOR_EXTRACT_ENTITIES, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_VALIDATOR_REVIEW_FULL_STORY, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_COMMUNITY_SUMMARIZER, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_SCENE_BLOCK_CONSOLIDATION, NOVEL_FORMAT_ZHIHU_SHORT),
    ("extractor_extract_changes", NOVEL_FORMAT_ZHIHU_SHORT),
    ("planner_brainstorm", NOVEL_FORMAT_ZHIHU_SHORT),
    ("planner_format_json", NOVEL_FORMAT_ZHIHU_SHORT),
    ("planner_chat_modify_outline", NOVEL_FORMAT_ZHIHU_SHORT),
    ("planner_optimize_skeleton_outline", NOVEL_FORMAT_ZHIHU_SHORT),
    ("planner_review_act_rhythm", NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE, NOVEL_FORMAT_LONG_WEBNOVEL),
    (PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE, NOVEL_FORMAT_LONG_WEBNOVEL),
    (AGENT_WRITER, NOVEL_FORMAT_LONG_WEBNOVEL),
    ("editor_review", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("editor_force_revise", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("editor_destyle", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("validator_validate_content", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("validator_extract_entities", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("extractor_summarize_changes", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("extractor_extract_changes", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("planner_chat_modify_outline", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("planner_optimize_skeleton_outline", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("planner_review_act_rhythm", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("issue_classifier_classify_issues", NOVEL_FORMAT_LONG_WEBNOVEL),
    ("community_summarizer", NOVEL_FORMAT_LONG_WEBNOVEL),
    (PROMPT_SCENE_BLOCK_CONSOLIDATION, NOVEL_FORMAT_LONG_WEBNOVEL),
)


async def find_missing_required_prompt_templates(
    db: AsyncSession,
) -> tuple[tuple[str, str], ...]:
    """Return required prompt keys absent from the runtime database."""
    names = {name for name, _category in REQUIRED_PROMPT_TEMPLATES}
    categories = {category for _name, category in REQUIRED_PROMPT_TEMPLATES}
    result = await db.execute(
        select(PromptTemplate.name, PromptTemplate.category).where(
            PromptTemplate.name.in_(names),
            PromptTemplate.category.in_(categories),
        )
    )
    present = set(result.all())
    return tuple(key for key in REQUIRED_PROMPT_TEMPLATES if key not in present)
