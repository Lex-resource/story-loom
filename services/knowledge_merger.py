import logging
import uuid
from typing import Any
from config import settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Novel, Chapter
from agents.constants import (
    AGENT_EXTRACTOR,
    AGENT_CHARACTER_CARD,
    AGENT_SCENE_CONSOLIDATOR,
)
from agents.pipeline import ExtractorNode
from agents.pipeline_context import PipelineContext
from services.workflow_surface import is_short_form_workflow
from services.stream_constants import STREAM_EVENT_CHARACTER_CARDS_UPDATED
from services.knowledge_patch_models import KnowledgePatchSet, KnowledgePatchSummary
from services.character_card_service import apply_character_card_updates
from services.character_card_bootstrap import (
    generate_initial_character_updates,
    merge_initial_character_updates,
)
from services.character_vector_service import enqueue_character_manifest_vectors
from services.character_constants import CHARACTER_CHAPTER_SOURCE_REF_TEMPLATE
from services.character_types import CharacterCardUpdate
from services.pipeline_transitions import publish_chapter_state
from services.pipeline_types import ChapterStatus
from services.project_stats import chapter_chars_from_row, sum_project_chars
from services.stream_manager import stream_manager
from services.stream_events import broadcast_extractor_phase
from services.novel_memory_evidence import capture_chapter_extractor_evidence
from services.novel_memory_atoms import (
    atom_conflict_issue,
    promote_reviewed_atom_candidates,
    reject_atom_candidates,
    reject_conflicting_atom_candidates,
    record_patch_atoms,
    review_atom_candidates,
    sync_world_rule_doctrines,
)
from services.novel_memory_conflicts import record_hard_conflicts
from services.novel_memory_lifecycle import sweep_stale_atom_candidates
from services.novel_memory_conflicts import (
    is_hard_extractor_issue,
    resolve_conflicts_automatically,
)
from services.novel_memory_scenes import aggregate_scene_block
from services.narrative_index import sync_narrative_index
from services.chapter_continuity import build_chapter_handoff
from services.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


async def _consolidate_scene_summary(
    db: AsyncSession,
    novel: Novel,
    chapter: Chapter,
    fallback_summary: str,
    accepted_atoms: list[Any],
) -> str:
    """Compress the chapter into a scene-block summary with the consolidation model.

    Best-effort by design: any failure or empty output returns "" so the caller
    falls back to the deterministic outline-summary / chapter-tail source.
    """
    try:
        from agents.scene_consolidator_agent import SceneConsolidatorAgent

        agent = SceneConsolidatorAgent()
        atom_statements = [
            str(getattr(atom, "statement", "") or "").strip()
            for atom in (accepted_atoms or [])
        ]
        atom_statements = [item for item in atom_statements if item][:12]
        summary = await agent.consolidate_scene_summary(
            novel_format=novel.novel_format,
            chapter_title=chapter.title or "",
            chapter_tail=(chapter.content or "")[-1500:],
            accepted_atoms=atom_statements,
            outline_summary=fallback_summary,
        )
        if summary:
            await agent.record_usage(
                db,
                novel.id,
                chapter.chapter_index,
                AGENT_SCENE_CONSOLIDATOR,
            )
        return summary
    except Exception:
        logger.exception(
            "scene_block_consolidation_failed project_id=%s chapter_index=%s",
            novel.id,
            chapter.chapter_index,
        )
        return ""

def append_extractor_review_flag(
    chapter: Chapter,
    high_risk_issues: list[dict],
    patch_set: KnowledgePatchSet | None = None,
    character_updates: list[dict] | None = None,
    conflict_records: list[Any] | None = None,
    automated: bool = False,
) -> None:
    flags = chapter.review_flags or []
    if not isinstance(flags, list):
        flags = []

    flag_type = "extractor_auto_review" if automated else "extractor_high_risk"
    existing_descriptions = {
        issue.get("description")
        for flag in flags
        if isinstance(flag, dict) and flag.get("type") == flag_type
        for issue in (flag.get("issues") or [])
        if isinstance(issue, dict)
    }
    new_issues = [
        issue for issue in high_risk_issues
        if issue.get("description") not in existing_descriptions
    ]
    if not new_issues:
        return

    flag_entry = {
        "type": flag_type,
        "severity": "warning",
        "message": (
            "系统已自动复核设定变更；冲突候选未覆盖既有事实。"
            if automated
            else "设定提取器发现高风险知识变更，需人工复核后发布。"
        ),
        "issues": new_issues,
    }
    if automated:
        flag_entry["decision"] = "reject_conflicting_candidates"
        flags = [
            flag for flag in flags
            if not (isinstance(flag, dict) and flag.get("type") == "extractor_high_risk")
        ]
    if patch_set is not None:
        flag_entry["patch_set"] = patch_set.model_dump()
    if character_updates:
        flag_entry["character_updates"] = character_updates
    if conflict_records:
        flag_entry["conflict_ids"] = [str(item.id) for item in conflict_records]
    chapter.review_flags = list(flags) + [flag_entry]


async def apply_extractor_updates(
    db: AsyncSession,
    novel: Novel,
    chapter: Chapter,
    extract_result: dict,
    *,
    ensure_active=None,
):
    """Apply extractor output to living docs, vector outbox, and chapter state.

    All canonical PostgreSQL projections for one chapter are committed once.
    The vector worker consumes outbox rows only after that commit, so a failed
    scene or narrative projection rolls back the complete publication.
    """
    chapter_index = chapter.chapter_index
    patch_set = KnowledgePatchSet.model_validate(extract_result)
    character_updates = _character_updates_from_extractor(extract_result)
    evidence = None
    if settings.ENABLE_NOVEL_MEMORY_EVIDENCE:
        evidence = await capture_chapter_extractor_evidence(
            db,
            project_id=novel.id,
            chapter_index=chapter_index,
            chapter_content=chapter.content or "",
            extractor_output=extract_result,
        )
    await broadcast_extractor_phase(novel.id, "writing")
    memory_atoms = []
    if settings.ENABLE_NOVEL_MEMORY_ATOMS:
        memory_atoms = await record_patch_atoms(
            db,
            project_id=novel.id,
            chapter_index=chapter_index,
            patch_set=patch_set,
            evidence_id=evidence.id if evidence is not None else None,
        )
    atom_reviews = await review_atom_candidates(db, memory_atoms)
    atom_conflict_issues = [
        issue
        for review in atom_reviews
        if (issue := atom_conflict_issue(review)) is not None
    ]
    high_risk_issues = [
        issue for issue in patch_set.raw_issues
        if is_hard_extractor_issue(issue)
    ]
    hard_issues = high_risk_issues + atom_conflict_issues
    conflict_records = await record_hard_conflicts(
        db,
        project_id=novel.id,
        chapter_index=chapter_index,
        issues=hard_issues,
    )
    if hard_issues and settings.ENABLE_AUTO_EXTRACTOR_REVIEW:
        if high_risk_issues:
            # A raw high-severity extractor issue has no reliable field-level
            # mapping, so keep every generated candidate out of canonical recall.
            reject_atom_candidates(memory_atoms)
        else:
            reject_conflicting_atom_candidates(atom_reviews)
        resolve_conflicts_automatically(conflict_records)
        append_extractor_review_flag(
            chapter,
            hard_issues,
            patch_set,
            character_updates=[item.model_dump(mode="json") for item in character_updates],
            conflict_records=conflict_records,
            automated=True,
        )
    elif hard_issues:
        chapter.status = ChapterStatus.PENDING_REVIEW
        append_extractor_review_flag(
            chapter,
            hard_issues,
            patch_set,
            character_updates=[item.model_dump(mode="json") for item in character_updates],
            conflict_records=conflict_records,
        )
        chapter.error = "设定提取器发现高风险知识变更，需人工复核后发布。"
        if ensure_active is not None:
            await ensure_active()
        await db.commit()
        return

    character_update_summary = await apply_character_card_updates(
        db,
        novel.id,
        chapter_index=chapter_index,
        updates=character_updates,
        source_ref=CHARACTER_CHAPTER_SOURCE_REF_TEMPLATE.format(chapter_index=chapter_index),
    )
    changed_character_names = [
        card.name for card in character_update_summary["changed_cards"]
    ]
    await enqueue_character_manifest_vectors(
        db,
        character_update_summary["changed_cards"],
        chapter_index=chapter_index,
    )
    patch_summary = KnowledgePatchSummary(
        changed_categorys=list(dict.fromkeys(patch.category for patch in patch_set.patches)),
        changed_items=[f"{patch.category}:{patch.name}" for patch in patch_set.patches],
        vector_items=[],
    )
    patch_summary.changed_items.extend(
        f"character_card:{card.name}" for card in character_update_summary["changed_cards"]
    )
    if character_update_summary["changed_cards"]:
        patch_summary.changed_categorys.append("character")
    # Canonical services succeeded, so only the reviewed candidates can be
    # promoted. Conflicting candidates returned above as review items.
    accepted_memory_atoms = promote_reviewed_atom_candidates(atom_reviews)
    if settings.ENABLE_NOVEL_MEMORY_RECALL:
        await sync_world_rule_doctrines(
            db,
            project_id=novel.id,
            atoms=accepted_memory_atoms,
        )

    if settings.ENABLE_CANDIDATE_LIFECYCLE_SWEEP:
        try:
            await sweep_stale_atom_candidates(
                db,
                project_id=novel.id,
                current_chapter=chapter_index,
                idle_chapters=settings.CANDIDATE_SWEEP_IDLE_CHAPTERS,
            )
        except Exception:
            logger.exception(
                "candidate_lifecycle_sweep_failed project_id=%s chapter_index=%s",
                novel.id,
                chapter_index,
            )

    publish_chapter_state(chapter)
    chapter.error = None
    novel.current_chapter = max(novel.current_chapter or 0, chapter_index)
    if (novel.total_chapters or 0) < chapter_index:
        novel.total_chapters = chapter_index
    word_count = chapter_chars_from_row(chapter)
    chapter.word_count = word_count
    novel.total_chars = await sum_project_chars(db, novel.id)

    if settings.ENABLE_NOVEL_MEMORY_SCENE_BLOCKS:
        outline = chapter.outline if isinstance(chapter.outline, dict) else {}
        summary = str(outline.get("summary") or (chapter.content or "")[:800]).strip()
        if settings.ENABLE_SCENE_BLOCK_CONSOLIDATION:
            summary = (
                await _consolidate_scene_summary(db, novel, chapter, summary, accepted_memory_atoms)
                or summary
            )
        recent_changes = [
            f"{patch.category}:{patch.name}:{patch.operation}"
            for patch in patch_set.patches
        ]
        open_questions = [
            str(issue.get("description") or issue.get("message"))
            for issue in patch_set.raw_issues
            if isinstance(issue, dict) and (issue.get("description") or issue.get("message"))
        ]
        await aggregate_scene_block(
            db,
            project_id=novel.id,
            scope_type="plotline",
            scope_key=str(outline.get("plotline") or "mainline"),
            summary=summary,
            current_state={
                "last_chapter": chapter_index,
                "chapter_title": chapter.title or "",
                "status": chapter.status,
            },
            open_questions=open_questions,
            recent_changes=recent_changes,
            source_ref=f"chapter:{chapter_index}:scene",
            source_chapter=chapter_index,
            valid_from_chapter=chapter_index,
        )

    if settings.ENABLE_NOVEL_NARRATIVE_INDEX:
        outline = chapter.outline if isinstance(chapter.outline, dict) else {}
        handoff = await build_chapter_handoff(
            db,
            novel.id,
            chapter_index + 1,
            previous_ending=(chapter.content or "")[-1800:],
        )
        await sync_narrative_index(
            db,
            project_id=novel.id,
            chapter_index=chapter_index,
            outline=outline,
            handoff=handoff.to_dict(),
            extractor_output=extract_result,
        )

    try:
        if ensure_active is not None:
            await ensure_active()
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "chapter_memory_publication_failed project_id=%s chapter_index=%s",
            novel.id,
            chapter_index,
        )
        raise

    from services.experiment_publication import record_published_chapter_for_project
    await record_published_chapter_for_project(
        db,
        novel.id,
        chapter_index,
        publication_source="post_processing",
    )

    if changed_character_names:
        await stream_manager.broadcast(
            str(novel.id),
            STREAM_EVENT_CHARACTER_CARDS_UPDATED,
            {
                "chapter_index": chapter_index,
                "character_names": changed_character_names,
            },
        )

    try:
        from services.issues import update_project_issue_summaries
        await update_project_issue_summaries(db, novel.id)
    except Exception:
        logger.exception("issue_summary_refresh_failed project_id=%s chapter_index=%s", novel.id, chapter_index)

    await _run_post_publication_reviews(db, novel, chapter_index)


async def _run_post_publication_reviews(
    db: AsyncSession,
    novel: Novel,
    chapter_index: int,
    *,
    include_volume: bool = True,
) -> None:
    """章节发布后的整篇/整卷复盘。短篇走整篇 review,长篇按卷触发。

    评审失败只记日志:复盘是发布后的附加动作,不能让它回滚已提交的章节。
    """
    if is_short_form_workflow(novel.novel_format):
        try:
            from services.short_story_review import review_completed_short_story
            await review_completed_short_story(db, novel, chapter_index)
        except Exception:
            logger.exception("short_story_review_failed project_id=%s chapter_index=%s", novel.id, chapter_index)
    elif include_volume:
        try:
            from services.volume_review import review_volume, volume_index_ending_at
            volume_index = volume_index_ending_at(novel.outline, chapter_index)
            if volume_index is not None:
                await review_volume(db, novel, volume_index)
        except Exception:
            logger.exception("volume_review_failed project_id=%s chapter_index=%s", novel.id, chapter_index)

async def run_post_processing(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    run_extractor: bool = True,
    ensure_active=None,
):
    result_novel = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result_novel.scalar_one_or_none()
    result_chapter = await db.execute(
        select(Chapter).where(Chapter.novel_id == novel_id, Chapter.chapter_index == chapter_index)
    )
    chapter = result_chapter.scalar_one_or_none()
    if not novel or not chapter:
        return

    if not run_extractor:
        publish_chapter_state(chapter)
        novel.current_chapter = max(novel.current_chapter or 0, chapter_index)
        if (novel.total_chapters or 0) < chapter_index:
            novel.total_chapters = chapter_index
        chapter.word_count = chapter_chars_from_row(chapter)
        novel.total_chars = await sum_project_chars(db, novel.id)
        if ensure_active is not None:
            await ensure_active()
        await db.commit()
        from services.experiment_publication import record_published_chapter_for_project
        await record_published_chapter_for_project(
            db,
            novel.id,
            chapter_index,
            publication_source="post_processing_without_extractor",
        )
        await _run_post_publication_reviews(db, novel, chapter_index, include_volume=False)
        return

    await broadcast_extractor_phase(novel.id, "startup")

    await broadcast_extractor_phase(novel.id, "analyzing")

    from services.character_context import build_extractor_character_context
    outline_data = chapter.outline if isinstance(chapter.outline, dict) else {}
    character_card_context = await build_extractor_character_context(
        db,
        novel.id,
        chapter.chapter_index,
        outline_data.get("characters_involved", []),
        outline_data,
        novel.outline if isinstance(novel.outline, dict) else None,
    )

    initial_character_updates, character_card_agent = await _generate_initial_cards(
        novel,
        chapter,
        character_card_context,
    )
    if character_card_agent is not None:
        await character_card_agent.record_usage(
            db,
            novel.id,
            chapter.chapter_index,
            AGENT_CHARACTER_CARD,
        )

    extractor_memory = await MemoryManager.get_context(
        db,
        novel.id,
        chapter.chapter_index,
        f"{chapter.title or ''} {chapter.content[:1000] if chapter.content else ''}",
        outline_data,
        agent_type="extractor",
    )
    extractor_context = PipelineContext.from_memory(
        str(novel.id),
        chapter.chapter_index,
        extractor_memory,
    )
    extractor_context.title = chapter.title or ""
    extractor_context.chapter_content = chapter.content or ""
    extractor_context.chapter_outline = outline_data
    extractor_context.character_card_context = character_card_context

    extractor = ExtractorNode()
    extractor.agent.project_id = novel.id
    extractor.agent.current_chapter = chapter.chapter_index

    extractor_output = await extractor.run(extractor_context, {"content": chapter.content})
    extract_result = extractor_output.payload
    await extractor.agent.record_usage(db, novel.id, chapter.chapter_index, AGENT_EXTRACTOR)

    if initial_character_updates:
        extracted_updates = _character_updates_from_extractor(extract_result)
        extract_result["character_updates"] = [
            update.model_dump(mode="json")
            for update in merge_initial_character_updates(
                initial_character_updates,
                extracted_updates,
            )
        ]

    # Capture the exact input/output pair before canonical knowledge merge.
    if ensure_active is None:
        await apply_extractor_updates(db, novel, chapter, extract_result)
    else:
        await apply_extractor_updates(
            db,
            novel,
            chapter,
            extract_result,
            ensure_active=ensure_active,
        )


async def _generate_initial_cards(
    novel: Novel,
    chapter: Chapter,
    character_card_context: str,
):
    try:
        return await generate_initial_character_updates(
            novel,
            chapter,
            character_card_context,
        )
    except Exception as exc:
        logger.warning(
            "initial_character_card_generation_failed project_id=%s chapter_index=%s error=%s",
            novel.id,
            chapter.chapter_index,
            exc,
        )
        return [], None


def _character_updates_from_extractor(extract_result: dict) -> list[CharacterCardUpdate]:
    """Read the new structured contract and adapt old character patches."""
    structured = extract_result.get("character_updates") if isinstance(extract_result, dict) else None
    if isinstance(structured, list) and structured:
        updates = [CharacterCardUpdate.model_validate(item) for item in structured]
        # The extractor is never trusted to grant itself first-card authority.
        return [update.model_copy(update={"card_data_authority": "extractor"}) for update in updates]

    legacy_updates: list[CharacterCardUpdate] = []
    patch_set = KnowledgePatchSet.model_validate(extract_result or {})
    for patch in patch_set.patches:
        if patch.category != "character":
            continue
        data = patch.data or {}
        attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
        relationships = data.get("relationships")
        if relationships is None:
            relationships = attributes.get("relationships", [])
        state_data = {
            key: value
            for key, value in {**attributes, **data}.items()
            if key not in {"relationships", "attributes", "body", "name", "category"}
        }
        body = data.get("body")
        if body:
            state_data["latest_observation"] = body
        legacy_updates.append(
            CharacterCardUpdate(
                character_name=patch.name,
                state_data=state_data,
                relationships=relationships if isinstance(relationships, list) else [],
                changed_fields=[f"state_data.{key}" for key in state_data],
            )
        )
    return legacy_updates
