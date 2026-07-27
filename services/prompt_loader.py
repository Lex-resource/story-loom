import os
import json
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.novel import PromptTemplate
from agents.constants import (
    AGENT_WRITER,
    NOVEL_FORMAT_LONG_WEBNOVEL,
    NOVEL_FORMAT_ZHIHU_SHORT,
    PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
    PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE,
    PROMPT_VALIDATOR_REVIEW_FULL_STORY,
)
from config import settings
from services.prompt_constants import PROMPT_CATEGORY_DIRS

logger = logging.getLogger(__name__)

REQUIRED_PROMPT_TEMPLATES: tuple[tuple[str, str], ...] = (
    (PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE, NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE, NOVEL_FORMAT_ZHIHU_SHORT),
    (AGENT_WRITER, NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_review", NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_force_revise", NOVEL_FORMAT_ZHIHU_SHORT),
    ("editor_destyle", NOVEL_FORMAT_ZHIHU_SHORT),
    ("validator_validate_content", NOVEL_FORMAT_ZHIHU_SHORT),
    (PROMPT_VALIDATOR_REVIEW_FULL_STORY, NOVEL_FORMAT_ZHIHU_SHORT),
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
)


async def seed_prompts_to_database(db: AsyncSession, *, overwrite_existing: bool = False):
    base_dir = Path(settings.PROMPTS_DIR)
    
    if not base_dir.exists():
        return

    for category_dir in PROMPT_CATEGORY_DIRS:
        dir_path = base_dir / category_dir
        if not dir_path.exists():
            continue
            
        for file_path in dir_path.glob("*.json"):
            try:
                content = file_path.read_text(encoding="utf-8")
                prompts = json.loads(content)
                if not isinstance(prompts, list):
                    continue
                    
                for p in prompts:
                    name = p.get("name")
                    category = p.get("category")
                    if not name or not category:
                        continue
                    
                    res = await db.execute(
                        select(PromptTemplate)
                        .where(PromptTemplate.name == name, PromptTemplate.category == category)
                    )
                    existing = res.scalar_one_or_none()
                    
                    if existing:
                        if overwrite_existing:
                            existing.name_zh = p.get("name_zh", existing.name_zh)
                            existing.system_prompt = p.get("system_prompt", existing.system_prompt)
                            existing.user_prompt_template = p.get("user_prompt_template", existing.user_prompt_template)
                            existing.is_default = p.get("is_default", existing.is_default)
                            existing.type = p.get("type", existing.type)
                    else:
                        new_tmpl = PromptTemplate(
                            name=name,
                            name_zh=p.get("name_zh"),
                            category=category,
                            type=p.get("type", category_dir),
                            system_prompt=p.get("system_prompt", ""),
                            user_prompt_template=p.get("user_prompt_template", ""),
                            is_default=p.get("is_default", 1)
                        )
                        db.add(new_tmpl)
            except Exception:
                logger.exception("prompt_seed_file_failed path=%s", file_path)
                
    try:
        await db.commit()
        logger.info("prompt_seed_completed")
        
        for name, category in REQUIRED_PROMPT_TEMPLATES:
            check_res = await db.execute(
                select(PromptTemplate)
                .where(PromptTemplate.name == name, PromptTemplate.category == category)
            )
            if not check_res.scalar_one_or_none():
                logger.warning("required_prompt_missing name=%s category=%s", name, category)
    except Exception:
        logger.exception("prompt_seed_commit_failed")


async def load_prompts_from_disk(db: AsyncSession):
    """Backward-compatible wrapper.

    Runtime prompt templates are database-owned. Disk JSON files are only seed
    data for missing rows and must not overwrite prompt edits made in the UI.
    """
    await seed_prompts_to_database(db, overwrite_existing=False)
