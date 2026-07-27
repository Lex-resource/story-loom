"""Context-building helpers for chapter generation."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import IssueSummary


USER_INTERVENTION_PREFIX = "用户实时插话干预："
SHORT_TERM_CONTEXT_HEADER = "【前序章节剧情线索（分级记忆短期缓存）】"
PREVIOUS_ENDING_HEADER = "【上一章结尾细节】"


def append_user_intervention(custom_prompt: str | None, intervention: str | None) -> str | None:
    if not intervention:
        return custom_prompt
    if custom_prompt:
        return f"{custom_prompt}\n- {USER_INTERVENTION_PREFIX}{intervention}"
    return f"{USER_INTERVENTION_PREFIX}{intervention}"


def with_short_term_context(previous_ending: str, short_term_context: str | None) -> str:
    if not short_term_context:
        return previous_ending
    return (
        f"{SHORT_TERM_CONTEXT_HEADER}\n{short_term_context}\n\n"
        f"{PREVIOUS_ENDING_HEADER}\n{previous_ending}"
    )


def append_succeeding_beginning_warning(
    previous_ending: str,
    succeeding_beginning: str,
    next_chapter: int,
) -> str:
    if not succeeding_beginning:
        return previous_ending
    return (
        f"{previous_ending}\n\n"
        f"【注意：后续章节（第{next_chapter + 1}章）的开头部分如下，本次策划必须与其逻辑契合，不可冲突】\n"
        f"{succeeding_beginning}"
    )


def succeeding_beginning_rewrite_message(succeeding_beginning: str, next_chapter: int) -> str:
    if not succeeding_beginning:
        return ""
    return (
        "【重要：请注意与后续章节的衔接】\n"
        f"以下是下一章（第{next_chapter + 1}章）的开头部分内容，本次重写必须保证与此内容在逻辑、剧情和细节上完美契合，绝对不可产生冲突：\n"
        f"{succeeding_beginning}\n"
    )


def append_block(base: str, block: str) -> str:
    if not block:
        return base
    return f"{base}\n{block}" if base else block


def writer_query_from_outline(outline_data: dict[str, Any]) -> str:
    return (
        f"{outline_data.get('title', '')} {outline_data.get('summary', '')} "
        f"{' '.join(outline_data.get('key_events', []))}"
    )


def rewrite_instructions_for_writer(
    custom_prompt: str | None,
    previous_error: str | None,
    succeeding_beginning: str,
    next_chapter: int,
) -> str:
    instructions = ""
    if custom_prompt:
        instructions = f"修改要求（自定义需求）：\n- {custom_prompt}\n"

    instructions = append_block(instructions, rewrite_instructions_from_error(previous_error))

    if succeeding_beginning:
        instructions = append_block(
            instructions,
            succeeding_beginning_rewrite_message(succeeding_beginning, next_chapter),
        )
    return instructions


def rewrite_instructions_from_error(previous_error: str | None) -> str:
    if not previous_error:
        return ""
    try:
        parsed_error = json.loads(previous_error)
    except Exception:
        return f"修改要求：\n{previous_error}"

    if isinstance(parsed_error, dict):
        instructions = ""
        if parsed_error.get("rewrite_instructions"):
            instructions = append_block(
                instructions,
                f"编辑重写指令：\n{parsed_error['rewrite_instructions']}",
            )
        if parsed_error.get("rewrite_reason"):
            instructions = append_block(
                instructions,
                f"打回原因：{parsed_error['rewrite_reason']}",
            )
        return instructions
    if isinstance(parsed_error, list):
        return "修改要求（未通过之前的审核）：\n" + "\n".join(
            f"- {error}" for error in parsed_error
        )
    return f"修改要求：\n{previous_error}"


async def load_issue_summaries(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = 10,
) -> str:
    result = await db.execute(
        select(IssueSummary).where(
            IssueSummary.project_id == project_id,
            IssueSummary.enabled == True,
        )
    )
    issues = result.scalars().all()
    return "\n".join([f"- {s.summary}" for s in issues[-limit:]])
