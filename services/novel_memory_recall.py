"""Progressive, scope-safe recall for novel agents."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryAtom, NovelSceneBlock, ProjectDoctrine
from services.context_compaction import compact_text, context_budget_for
from services.novel_memory_types import (
    ATOM_STATUS_ACCEPTED,
    ATOM_STATUS_CANDIDATE,
    SCENE_BLOCK_ACTIVE,
    STORYLINE_MAIN,
)
from services.novel_memory_ranking import (
    _latest_atoms_by_key,
    _latest_scene_blocks,
    lexical_recall_score,
    rank_recall_items,
)
from services.vector_constants import VECTOR_COLLECTION_PREFIX

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecallBudget:
    doctrine_limit: int
    scene_limit: int
    atom_limit: int
    due_atom_limit: int
    max_chars: int
    candidate_limit: int = 4


@dataclass(frozen=True)
class AgentRecallProfile:
    """单个 agent 角色的全部召回配置。

    召回预算、向量建议、类型白名单此前散落在 5 个平级 dict + memory_manager
    的内联 dict 里,新增角色要改 6 处;现在收进一张表 —— 新增角色只加一行,
    完整性由 tests/services/test_agent_recall_profiles.py 守恒。
    """

    budget: RecallBudget
    hybrid_vector_limit: int
    hybrid_vector_sources: tuple[str, ...]
    atom_types: tuple[str, ...]
    scene_types: tuple[str, ...]
    narrative_index_chars: int


AGENT_RECALL_PROFILES: dict[str, AgentRecallProfile] = {
    "planner": AgentRecallProfile(
        budget=RecallBudget(8, 6, 12, 4, 9000),
        hybrid_vector_limit=4,
        hybrid_vector_sources=("scene_block",),
        atom_types=("plot_thread", "foreshadowing", "character_state"),
        scene_types=("plotline", "character_arc"),
        narrative_index_chars=1000,
    ),
    "writer": AgentRecallProfile(
        budget=RecallBudget(4, 4, 8, 3, 6500),
        hybrid_vector_limit=4,
        hybrid_vector_sources=("scene_block", "chapter_extract"),
        atom_types=("world_rule", "character_state", "foreshadowing"),
        scene_types=("plotline", "character_arc"),
        narrative_index_chars=800,
    ),
    "editor": AgentRecallProfile(
        budget=RecallBudget(4, 4, 10, 3, 7000),
        hybrid_vector_limit=3,
        hybrid_vector_sources=("scene_block", "chapter_extract"),
        atom_types=("world_rule", "character_state", "foreshadowing", "plot_thread"),
        scene_types=("plotline", "character_arc"),
        narrative_index_chars=800,
    ),
    "validator": AgentRecallProfile(
        budget=RecallBudget(6, 6, 16, 6, 10000),
        hybrid_vector_limit=4,
        hybrid_vector_sources=("scene_block", "chapter_extract"),
        atom_types=("world_rule", "character_state", "foreshadowing", "plot_thread"),
        scene_types=("plotline", "character_arc"),
        narrative_index_chars=900,
    ),
    "extractor": AgentRecallProfile(
        budget=RecallBudget(4, 3, 12, 4, 7000),
        hybrid_vector_limit=3,
        hybrid_vector_sources=("scene_block", "chapter_extract"),
        atom_types=("world_rule", "character_state", "foreshadowing", "plot_thread"),
        scene_types=("plotline", "character_arc"),
        narrative_index_chars=600,
    ),
}
_DEFAULT_PROFILE_AGENT = "writer"

# 兼容旧名:测试与外部代码仍按 agent->dict 的形状导入。
RECALL_BUDGETS: dict[str, RecallBudget] = {
    name: profile.budget for name, profile in AGENT_RECALL_PROFILES.items()
}
HYBRID_VECTOR_LIMITS: dict[str, int] = {
    name: profile.hybrid_vector_limit for name, profile in AGENT_RECALL_PROFILES.items()
}
HYBRID_VECTOR_SOURCES: dict[str, set[str]] = {
    name: set(profile.hybrid_vector_sources) for name, profile in AGENT_RECALL_PROFILES.items()
}
_AGENT_ATOM_TYPES: dict[str, set[str]] = {
    name: set(profile.atom_types) for name, profile in AGENT_RECALL_PROFILES.items()
}
_AGENT_SCENE_TYPES: dict[str, set[str]] = {
    name: set(profile.scene_types) for name, profile in AGENT_RECALL_PROFILES.items()
}

# A4 uses a larger deterministic PostgreSQL candidate pool, then ranks the
# bounded rows locally. This keeps the query portable and avoids a schema or
# model-call dependency while still escaping the old "latest rows only" bias.
LEXICAL_RECALL_POOL_MULTIPLIER = 4


def profile_for(agent_type: str) -> AgentRecallProfile:
    return AGENT_RECALL_PROFILES.get(agent_type, AGENT_RECALL_PROFILES[_DEFAULT_PROFILE_AGENT])


@dataclass
class NovelMemoryRecall:
    doctrines: list[ProjectDoctrine]
    scene_blocks: list[NovelSceneBlock]
    atoms: list[NovelMemoryAtom]
    due_atoms: list[NovelMemoryAtom]
    candidate_atoms: list[NovelMemoryAtom]
    context: str
    # 本次实际注入 prompt 的 atom 清单 —— 命中簿记由调用方
    # (memory_manager → lifecycle.record_recall_hits)落库,recall 自身保持只读。
    injected_atoms: list[NovelMemoryAtom] | None = None


async def _retrieve_vector_advisory_context(
    project_id,
    chapter_index: int,
    query_text: str,
    agent_type: str,
) -> str:
    """Retrieve only advisory historical projections from the project Chroma collection."""
    if not str(query_text or "").strip():
        return ""
    profile = profile_for(agent_type)
    allowed_sources = profile.hybrid_vector_sources
    result_limit = profile.hybrid_vector_limit
    try:
        # Import lazily so PostgreSQL-only unit tests do not initialize Chroma.
        from services.vector_chroma import has_collection_documents, query_collection

        # Do not make an empty project pay the local embedding initialization
        # cost. The first chapter has no historical projection by definition.
        if not await has_collection_documents(f"{VECTOR_COLLECTION_PREFIX}{project_id}"):
            return ""

        result = await query_collection(
            collection_name=f"{VECTOR_COLLECTION_PREFIX}{project_id}",
            query_texts=[str(query_text)[:2000]],
            n_results=max(result_limit * 3, result_limit),
        )
    except Exception:
        logger.exception(
            "novel_memory_vector_recall_failed project_id=%s chapter_index=%s agent=%s",
            project_id,
            chapter_index,
            agent_type,
        )
        return ""

    documents = (result or {}).get("documents", [[]])
    metadatas = (result or {}).get("metadatas", [[]])
    distances = (result or {}).get("distances", [[]])
    documents = documents[0] if documents else []
    metadatas = metadatas[0] if metadatas else []
    distances = distances[0] if distances else []
    lines: list[str] = []
    seen: set[str] = set()
    for index, document in enumerate(documents or []):
        metadata = metadatas[index] if index < len(metadatas) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        source = str(metadata.get("source") or "")
        if source not in allowed_sources:
            continue
        source_chapter = metadata.get("chapter_index")
        try:
            source_chapter_int = int(source_chapter)
        except (TypeError, ValueError):
            source_chapter_int = 0
        if source_chapter_int > chapter_index:
            continue
        text = str(document or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        label = f"第{source_chapter_int}章" if source_chapter_int else "章节未标注"
        name = str(metadata.get("name") or "").strip()
        name_prefix = f" {name}:" if name else ""
        distance = distances[index] if index < len(distances) else None
        score = f" distance={float(distance):.4f}" if isinstance(distance, (int, float)) else ""
        lines.append(f"- [retrieved_advisory/{label}/{source}{score}]{name_prefix} {text}")
        if len(lines) >= result_limit:
            break
    return "\n".join(lines)


def budget_for(agent_type: str) -> RecallBudget:
    return profile_for(agent_type).budget


def narrative_index_chars_for(agent_type: str) -> int:
    """叙事索引的 per-agent 字符预算(单一来源:AgentRecallProfile)。"""
    return profile_for(agent_type).narrative_index_chars


async def recall_novel_memory(
    db: AsyncSession,
    *,
    project_id,
    chapter_index: int,
    agent_type: str = "writer",
    branch_id=None,
    storyline_id: str = STORYLINE_MAIN,
    query_text: str = "",
    include_vector: bool = False,
) -> NovelMemoryRecall:
    """Recall scoped memory with deterministic lexical and optional vector ranking."""
    budget = budget_for(agent_type)
    max_context_chars = (
        context_budget_for(agent_type).memory_chars
    )
    empty = NovelMemoryRecall([], [], [], [], [], "")
    try:
        scope = (
            NovelMemoryAtom.project_id == project_id,
            NovelMemoryAtom.branch_id == branch_id,
            NovelMemoryAtom.storyline_id == storyline_id,
        )
        doctrine_scope = (
            ProjectDoctrine.project_id == project_id,
            ProjectDoctrine.branch_id == branch_id,
            ProjectDoctrine.storyline_id == storyline_id,
            ProjectDoctrine.is_active.is_(True),
        )
        time_scope = lambda model: and_(
            or_(model.valid_from_chapter.is_(None), model.valid_from_chapter <= chapter_index),
            or_(model.valid_to_chapter.is_(None), model.valid_to_chapter >= chapter_index),
        )
        doctrines = list((await db.scalars(
            select(ProjectDoctrine).where(*doctrine_scope).order_by(ProjectDoctrine.version.desc()).limit(
                budget.doctrine_limit * LEXICAL_RECALL_POOL_MULTIPLIER
            )
        )).all())
        scenes = list((await db.scalars(
            select(NovelSceneBlock).where(
                NovelSceneBlock.project_id == project_id,
                NovelSceneBlock.branch_id == branch_id,
                NovelSceneBlock.storyline_id == storyline_id,
                NovelSceneBlock.status == SCENE_BLOCK_ACTIVE,
                time_scope(NovelSceneBlock),
            ).order_by(NovelSceneBlock.source_chapter.desc(), NovelSceneBlock.version.desc()).limit(
                budget.scene_limit * LEXICAL_RECALL_POOL_MULTIPLIER
            )
        )).all())
        recalled_atoms = list((await db.scalars(
            select(NovelMemoryAtom).where(
                *scope,
                NovelMemoryAtom.status.in_((ATOM_STATUS_ACCEPTED, ATOM_STATUS_CANDIDATE)),
                time_scope(NovelMemoryAtom),
            ).order_by(NovelMemoryAtom.source_chapter.desc(), NovelMemoryAtom.version.desc()).limit(
                max(budget.atom_limit, budget.candidate_limit) * LEXICAL_RECALL_POOL_MULTIPLIER
            )
        )).all())
        doctrines = rank_recall_items(
            doctrines,
            query_text,
            limit=budget.doctrine_limit,
            text_getter=lambda item: str(getattr(item, "content", "")),
        )
        scenes = rank_recall_items(
            _latest_scene_blocks(scenes),
            query_text,
            limit=budget.scene_limit,
            text_getter=lambda item: " ".join(
                [
                    str(getattr(item, "scope_key", "")),
                    str(getattr(item, "summary", "")),
                    str(getattr(item, "open_questions", "")),
                    str(getattr(item, "recent_changes", "")),
                ]
            ),
        )
        ranked_atoms = rank_recall_items(
            recalled_atoms,
            query_text,
            limit=max(budget.atom_limit, budget.candidate_limit) * LEXICAL_RECALL_POOL_MULTIPLIER,
            text_getter=lambda item: str(getattr(item, "statement", "")),
        )
        atoms = _latest_atoms_by_key(
            [item for item in ranked_atoms if item.status == ATOM_STATUS_ACCEPTED]
        )[:budget.atom_limit]
        candidate_atoms = [
            item for item in _latest_atoms_by_key(
                [item for item in ranked_atoms if item.status == ATOM_STATUS_CANDIDATE]
            )
        ][:budget.candidate_limit]
        due_atoms = _latest_atoms_by_key(list((await db.scalars(
            select(NovelMemoryAtom).where(
                *scope,
                NovelMemoryAtom.status == ATOM_STATUS_ACCEPTED,
                NovelMemoryAtom.atom_type == "foreshadowing",
                NovelMemoryAtom.valid_to_chapter.is_not(None),
                NovelMemoryAtom.valid_to_chapter <= chapter_index,
            ).order_by(NovelMemoryAtom.valid_to_chapter.asc()).limit(budget.due_atom_limit)
        )).all()))
        hybrid_context = ""
        if include_vector:
            hybrid_context = await _retrieve_vector_advisory_context(
                project_id,
                chapter_index,
                query_text,
                agent_type,
            )
        injected_keys = [
            str(getattr(item, "memory_key", "") or "")
            for item in (*atoms, *due_atoms, *candidate_atoms)
            if str(getattr(item, "memory_key", "") or "")
        ]
        from services.experiment_recorder import record_event

        record_event(
            "memory_recall",
            {
                "agent_type": agent_type,
                "query_chars": len(str(query_text or "")),
                "lexical_candidate_pool": len(recalled_atoms) + len(scenes) + len(doctrines),
                "accepted_atom_count": len(atoms),
                "candidate_atom_count": len(candidate_atoms),
                "vector_advisory_count": len(hybrid_context.splitlines()) if hybrid_context else 0,
                "hybrid_enabled": bool(include_vector),
                "injected_memory_keys": injected_keys[:50],
            },
        )
        return NovelMemoryRecall(
            doctrines=doctrines,
            scene_blocks=scenes,
            atoms=atoms,
            due_atoms=due_atoms,
            candidate_atoms=candidate_atoms,
            context=format_recall_context(
                doctrines,
                scenes,
                atoms,
                due_atoms,
                max_context_chars,
                agent_type=agent_type,
                candidate_atoms=candidate_atoms,
                hybrid_context=hybrid_context,
            ),
            injected_atoms=[*atoms, *due_atoms, *candidate_atoms],
        )
    except Exception:
        logger.exception(
            "novel_memory_recall_failed project_id=%s chapter_index=%s agent=%s",
            project_id,
            chapter_index,
            agent_type,
        )
        # Recall is advisory. Roll back a failed read transaction so callers
        # can continue using the canonical context on the same session.
        try:
            await db.rollback()
        except Exception:
            logger.exception("novel_memory_recall_rollback_failed")
        return empty


def format_recall_context(
    doctrines: list[Any],
    scene_blocks: list[Any],
    atoms: list[Any],
    due_atoms: list[Any],
    max_chars: int,
    *,
    agent_type: str = "writer",
    candidate_atoms: list[Any] | None = None,
    hybrid_context: str = "",
) -> str:
    allowed_types = _AGENT_ATOM_TYPES.get(agent_type, _AGENT_ATOM_TYPES["writer"])
    allowed_scene_types = _AGENT_SCENE_TYPES.get(agent_type, _AGENT_SCENE_TYPES["writer"])
    scene_blocks = [
        item
        for item in scene_blocks
        if getattr(item, "scope_type", None) in allowed_scene_types
    ]
    scene_blocks = _latest_scene_blocks(scene_blocks)
    atoms = [
        item for item in atoms
        if getattr(item, "atom_type", None) in allowed_types
    ]
    atoms = _latest_atoms_by_key(atoms)
    candidate_atoms = [
        item
        for item in (candidate_atoms or [])
        if getattr(item, "atom_type", None) in allowed_types
    ]
    candidate_atoms = _latest_atoms_by_key(candidate_atoms)
    due_atoms = _latest_atoms_by_key(due_atoms)

    seen_statements: set[str] = set()

    def unique(items: list[Any]) -> list[Any]:
        result: list[Any] = []
        for item in items:
            statement = str(getattr(item, "statement", "") or "").strip()
            if not statement or statement in seen_statements:
                continue
            seen_statements.add(statement)
            result.append(item)
        return result

    atoms = unique(atoms)
    due_atoms = unique(due_atoms)
    candidate_atoms = unique(candidate_atoms)

    def fact_line(item: Any) -> str:
        status = str(getattr(item, "status", "accepted") or "accepted")
        authority = str(getattr(item, "authority", "accepted") or "accepted")
        authority_label = "accepted" if status == "accepted" else authority
        source_chapter = getattr(item, "source_chapter", None)
        source = f"第{source_chapter}章" if source_chapter else "来源未标注"
        return f"- [{authority_label}/{source}] {item.statement}"

    def candidate_line(item: Any) -> str:
        source_chapter = getattr(item, "source_chapter", None)
        source = f"第{source_chapter}章" if source_chapter else "来源未标注"
        return f"- [candidate/generated/{source}] {item.statement}"

    sections: list[tuple[str, list[str]]] = []
    if doctrines:
        sections.append(("【项目原则】", [f"- {item.content}" for item in doctrines]))
    if scene_blocks:
        sections.append(("【当前场景块】", [
            f"- [{item.scope_type}/{item.scope_key}] {item.summary}"
            for item in scene_blocks
        ]))
    if atoms:
        sections.append(("【已确认记忆】", [fact_line(item) for item in atoms]))
    if due_atoms:
        sections.append(("【到期伏笔】", [fact_line(item) for item in due_atoms]))
    if hybrid_context:
        sections.append(("【历史相关片段（向量建议）】", hybrid_context.splitlines()))
    if candidate_atoms:
        sections.append((
            "【待核对记忆线索（禁止当作事实）】",
            [candidate_line(item) for item in candidate_atoms]
            + ["只能将这些内容写成观察、疑问或待验证线索，不能据此确认身份、因果或状态。"],
        ))

    rendered: list[str] = []
    used = 0
    for header, lines in sections:
        if used >= max_chars:
            break
        separator = "\n\n" if rendered else ""
        header_text = separator + header
        if used + len(header_text) > max_chars:
            break
        block = header_text
        for line in lines:
            candidate = f"{block}\n{line}"
            if len(candidate) <= max_chars - used:
                block = candidate
                continue
            remaining = max_chars - used - len(block) - 1
            if remaining > 40:
                block = f"{block}\n{compact_text(line, remaining)}"
            break
        rendered.append(block)
        used += len(block)

    return "".join(rendered)[:max(0, max_chars)]


def _compact_key(value: str) -> str:
    value = re.sub(r"^\s*[-*•]+\s*", "", value or "")
    return "".join(value.split()).casefold()


def merge_layered_context(
    character_manifest_context: str,
    novel_memory_context: str,
    max_chars: int,
) -> str:
    """Combine stable character facts and layered recall into one prompt block.

    Character manifests are the stable authority. Layered memory only adds
    chapter-scoped facts and scene state; exact facts already present in the
    manifest are omitted to avoid spending context twice.
    """
    manifest = (character_manifest_context or "").strip()
    memory = (novel_memory_context or "").strip()
    if not manifest and not memory:
        return ""

    manifest_key = _compact_key(manifest)
    filtered_lines: list[str] = []
    seen_lines: set[str] = set()
    for line in memory.splitlines():
        key = _compact_key(line)
        if not key or key in seen_lines:
            continue
        seen_lines.add(key)
        if key.startswith("【"):
            filtered_lines.append(line)
            continue
        if manifest_key and key in manifest_key:
            continue
        filtered_lines.append(line)
    memory = "\n".join(filtered_lines).strip()

    sections: list[str] = []
    if manifest:
        sections.append(
            "【角色卡稳定事实（权威来源）】\n"
            + manifest
        )
    if memory:
        sections.append(
            "【分层记忆补充（只补充角色卡未覆盖的章节变化）】\n"
            + memory
            + "\n若与角色卡或本章大纲冲突，以角色卡和本章大纲为准。"
        )
    merged = "\n\n".join(sections)
    return compact_text(merged, max_chars, tail_chars=max(1, max_chars // 4))


def remove_authority_duplicates(
    authority_context: str,
    supplemental_context: str,
    max_chars: int,
) -> str:
    """Remove supplemental lines already represented by an authority block."""
    authority = (authority_context or "").strip()
    supplemental = (supplemental_context or "").strip()
    if not supplemental:
        return ""
    authority_key = _compact_key(authority)
    seen: set[str] = set()
    kept: list[str] = []
    for line in supplemental.splitlines():
        key = _compact_key(line)
        compare_key = key.split("]", 1)[1] if key.startswith("[") and "]" in key else key
        if not key or compare_key in seen:
            continue
        seen.add(compare_key)
        if key.startswith("【"):
            kept.append(line)
            continue
        if authority_key and compare_key in authority_key:
            continue
        kept.append(line)
    return compact_text("\n".join(kept).strip(), max_chars, tail_chars=max(1, max_chars // 4))
