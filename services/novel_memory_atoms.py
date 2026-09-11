"""Controlled conversion of extractor patches into candidate memory atoms."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryAtom, ProjectDoctrine
from services.knowledge_patch_models import KnowledgePatch, KnowledgePatchSet
from services.novel_memory_evidence import chapter_evidence_source_ref
from services.novel_memory_types import (
    AUTHORITY_GENERATED,
    ATOM_STATUS_CANDIDATE,
    ATOM_STATUS_ACCEPTED,
    ATOM_STATUS_REJECTED,
    ATOM_STATUS_SUPERSEDED,
    ATOM_STATUSES,
    STORYLINE_MAIN,
)


PATCH_ATOM_TYPE = {
    "character": "character_state",
    "world_rule": "world_rule",
    "foreshadowing": "foreshadowing",
    "plot_thread": "plot_thread",
}

_PROTECTED_AUTHORITIES = frozenset({"published", "user", "frozen", "system"})
_WORLD_RULE_OBSERVATION_FIELDS = frozenset({
    "adjacent_element",
    "access_boundary",
    "capabilities",
    "confirmed_behavior",
    "confirmed_state",
    "current_state",
    "current_status",
    "device_state",
    "evidence_boundary",
    "evidence_level",
    "layout",
    "location",
    "limitations",
    "observed_records",
    "observed_state",
    "obscured_fields",
    "scope",
    "state",
    "response_scope",
    "status",
    "uncertainty",
    "visible_fields",
    "visible_structure",
    "displayed_receipt",
})
_REPLACEMENT_MARKERS = frozenset({
    "replace",
    "replacement",
    "explicit_replacement",
    "replace_existing",
    "supersedes",
})

_WORLD_RULE_TYPE_ALIASES = frozenset({"rule", "confirmed"})


@dataclass(frozen=True)
class AtomCandidateReview:
    """Database review result before a generated atom can be promoted."""

    atom: NovelMemoryAtom
    accepted_atom: NovelMemoryAtom | None
    conflict: bool


def _is_explicit_transition(atom: NovelMemoryAtom) -> bool:
    operation = str((atom.data or {}).get("operation") or "").strip().lower()
    return operation in {"append_progress", "resolve", "cancel"}


def _atom_operation(atom: NovelMemoryAtom) -> str:
    return str((getattr(atom, "data", None) or {}).get("operation") or "").strip().lower()


def _atom_payload(atom: NovelMemoryAtom) -> dict[str, Any]:
    data = getattr(atom, "data", None)
    if not isinstance(data, dict):
        return {}
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


def _has_explicit_replacement(atom: NovelMemoryAtom) -> bool:
    """Recognize an intentional replacement without trusting free-form prose."""
    payload = _atom_payload(atom)
    for key in _REPLACEMENT_MARKERS:
        value = payload.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "yes", "replace"}:
            return True
    return str(payload.get("update_kind") or "").strip().lower() in _REPLACEMENT_MARKERS


def _stable_field_conflict(atom: NovelMemoryAtom, accepted: NovelMemoryAtom) -> bool:
    """Catch a changed hard marker even when a model labels it as progress."""
    candidate = _atom_payload(atom)
    previous = _atom_payload(accepted)
    for key in ("rule_type", "confirmed", "frozen", "locked"):
        if key in candidate and key in previous and candidate[key] != previous[key]:
            if (
                key == "rule_type"
                and {
                    str(candidate[key]).strip().lower(),
                    str(previous[key]).strip().lower(),
                }
                <= _WORLD_RULE_TYPE_ALIASES
            ):
                continue
            return True
    return False


def _is_observational_merge(atom: NovelMemoryAtom, accepted: NovelMemoryAtom) -> bool:
    """Allow observed generated state evolution without arbitrary replacement.

    World-rule observations may use display/layout fields that are not part of
    the original rule declaration. Hard markers are checked separately before
    this field allow-list is consulted.
    """
    if _atom_operation(atom) != "merge":
        return False
    if str(getattr(accepted, "authority", AUTHORITY_GENERATED) or "").lower() in _PROTECTED_AUTHORITIES:
        return False
    if _has_explicit_replacement(atom) or _stable_field_conflict(atom, accepted):
        return False
    if atom.atom_type == "character_state":
        return True
    if atom.atom_type == "world_rule":
        return bool(_WORLD_RULE_OBSERVATION_FIELDS.intersection(_atom_payload(atom)))
    return False


def _is_safe_atom_progression(atom: NovelMemoryAtom, accepted: NovelMemoryAtom) -> bool:
    """Return whether a changed candidate can supersede the accepted projection."""
    if accepted.statement == atom.statement:
        return True
    accepted_authority = str(getattr(accepted, "authority", AUTHORITY_GENERATED) or "").lower()
    if accepted_authority in _PROTECTED_AUTHORITIES:
        return False
    if _has_explicit_replacement(atom):
        return True
    if _stable_field_conflict(atom, accepted):
        return False
    return _is_explicit_transition(atom) or _is_observational_merge(atom, accepted)


def atom_conflict_issue(review: AtomCandidateReview) -> dict[str, Any] | None:
    if not review.conflict or review.accepted_atom is None:
        return None
    return {
        "conflict_type": "accepted_memory_atom",
        "category": review.atom.atom_type,
        "memory_key": review.atom.memory_key,
        "severity": "high",
        "description": f"生成候选与已接受记忆冲突：{review.atom.memory_key}",
        "evidence": review.atom.statement,
        "conflicts_with": review.accepted_atom.statement,
        "source_ref": review.atom.source_ref,
        "candidate_id": str(review.atom.id),
        "accepted_id": str(review.accepted_atom.id),
    }


def transition_atom_status(atom: NovelMemoryAtom, status: str) -> NovelMemoryAtom:
    """Apply an explicit review decision to an atom, never to canonical facts."""
    if status not in ATOM_STATUSES:
        raise ValueError(f"Invalid novel memory atom status: {status}")
    if atom.status not in {ATOM_STATUS_CANDIDATE, ATOM_STATUS_ACCEPTED}:
        raise ValueError(f"Atom cannot transition from status: {atom.status}")
    atom.status = status
    return atom


def accept_atom_candidates(atoms: list[NovelMemoryAtom]) -> list[NovelMemoryAtom]:
    return [transition_atom_status(atom, ATOM_STATUS_ACCEPTED) for atom in atoms]


def reject_atom_candidate(atom: NovelMemoryAtom) -> NovelMemoryAtom:
    return transition_atom_status(atom, ATOM_STATUS_REJECTED)


def supersede_atom(atom: NovelMemoryAtom) -> NovelMemoryAtom:
    return transition_atom_status(atom, ATOM_STATUS_SUPERSEDED)


def build_atom_candidate_hash(patch: KnowledgePatch) -> str:
    payload = patch.model_dump(mode="json")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _confidence_from_patch(patch: KnowledgePatch) -> float:
    value = patch.data.get("confidence", 0.5)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _statement_for_patch(patch: KnowledgePatch, chapter_index: int) -> str:
    body = patch.data.get("body") or patch.data.get("description") or patch.data.get("progress")
    if body:
        return str(body)
    data = json.dumps(patch.data, ensure_ascii=False, sort_keys=True, default=str)
    return f"第{chapter_index}章 {patch.operation} {patch.category}/{patch.name}: {data}"


def _atom_values(
    patch: KnowledgePatch,
    *,
    project_id: uuid.UUID,
    chapter_index: int,
    evidence_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    storyline_id: str,
    version: int,
) -> dict[str, Any]:
    data = patch.model_dump(mode="json")
    valid_to = patch.data.get("valid_to_chapter")
    return {
        "project_id": project_id,
        "branch_id": branch_id,
        "storyline_id": storyline_id,
        "source_ref": chapter_evidence_source_ref(chapter_index),
        "source_chapter": chapter_index,
        "confidence": _confidence_from_patch(patch),
        "version": version,
        "valid_from_chapter": chapter_index,
        "valid_to_chapter": int(valid_to) if valid_to is not None else None,
        "authority": AUTHORITY_GENERATED,
        "evidence_id": evidence_id,
        "memory_key": f"{patch.category}:{patch.name}",
        "candidate_hash": build_atom_candidate_hash(patch),
        "atom_type": PATCH_ATOM_TYPE.get(patch.category, patch.category),
        "statement": _statement_for_patch(patch, chapter_index),
        "data": data,
        "status": ATOM_STATUS_CANDIDATE,
    }


async def record_patch_atoms(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_index: int,
    patch_set: KnowledgePatchSet,
    evidence_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> list[NovelMemoryAtom]:
    """Persist extractor patches as candidates without mutating canonical data."""
    persisted: list[NovelMemoryAtom] = []
    for patch in patch_set.patches:
        candidate_hash = build_atom_candidate_hash(patch)
        memory_key = f"{patch.category}:{patch.name}"
        for _attempt in range(5):
            max_version = await db.scalar(
                select(func.max(NovelMemoryAtom.version)).where(
                    NovelMemoryAtom.project_id == project_id,
                    NovelMemoryAtom.branch_id == branch_id,
                    NovelMemoryAtom.storyline_id == storyline_id,
                    NovelMemoryAtom.memory_key == memory_key,
                )
            )
            values = _atom_values(
                patch,
                project_id=project_id,
                chapter_index=chapter_index,
                evidence_id=evidence_id,
                branch_id=branch_id,
                storyline_id=storyline_id,
                version=int(max_version or 0) + 1,
            )
            await db.execute(pg_insert(NovelMemoryAtom).values(**values).on_conflict_do_nothing())
            atom = await db.scalar(
                select(NovelMemoryAtom).where(
                    NovelMemoryAtom.project_id == project_id,
                    NovelMemoryAtom.branch_id == branch_id,
                    NovelMemoryAtom.storyline_id == storyline_id,
                    NovelMemoryAtom.memory_key == memory_key,
                    NovelMemoryAtom.candidate_hash == candidate_hash,
                )
            )
            if atom is not None:
                persisted.append(atom)
                break
        else:
            raise RuntimeError(f"Could not persist memory atom candidate: {memory_key}")
    return persisted


async def review_atom_candidates(
    db: AsyncSession,
    atoms: list[NovelMemoryAtom],
) -> list[AtomCandidateReview]:
    """Compare candidates with the latest accepted atom in their namespace.

    The extractor emits chapter-local observations against stable memory keys.
    A changed generated character state or observation-shaped world rule is a
    normal projection update; an explicit replacement is also allowed for a
    generated atom. Protected user/published/frozen/system facts, or changed
    hard markers, still require review.
    """
    reviews: list[AtomCandidateReview] = []
    for atom in atoms:
        if atom.status != ATOM_STATUS_CANDIDATE:
            reviews.append(AtomCandidateReview(atom, None, False))
            continue
        accepted = await db.scalar(
            select(NovelMemoryAtom)
            .where(
                NovelMemoryAtom.project_id == atom.project_id,
                NovelMemoryAtom.branch_id == atom.branch_id,
                NovelMemoryAtom.storyline_id == atom.storyline_id,
                NovelMemoryAtom.memory_key == atom.memory_key,
                NovelMemoryAtom.status == ATOM_STATUS_ACCEPTED,
            )
            .order_by(NovelMemoryAtom.version.desc())
            .limit(1)
            .with_for_update()
        )
        conflict = bool(
            accepted is not None
            and not _is_safe_atom_progression(atom, accepted)
        )
        reviews.append(AtomCandidateReview(atom, accepted, conflict))
    return reviews


def promote_reviewed_atom_candidates(
    reviews: list[AtomCandidateReview],
) -> list[NovelMemoryAtom]:
    """Promote only reviewed candidates; never overwrite a conflicting fact."""
    promoted: list[NovelMemoryAtom] = []
    for review in reviews:
        if review.conflict:
            continue
        if (
            review.accepted_atom is not None
            and review.accepted_atom.statement != review.atom.statement
        ):
            review.accepted_atom.status = ATOM_STATUS_SUPERSEDED
        if review.atom.status == ATOM_STATUS_CANDIDATE:
            review.atom.status = ATOM_STATUS_ACCEPTED
        if review.atom.status == ATOM_STATUS_ACCEPTED:
            promoted.append(review.atom)
    return promoted


def reject_atom_candidates(
    atoms: list[NovelMemoryAtom],
) -> list[NovelMemoryAtom]:
    """Reject generated candidates that automatic review cannot safely apply."""
    rejected: list[NovelMemoryAtom] = []
    for atom in atoms:
        if atom.status != ATOM_STATUS_CANDIDATE:
            continue
        atom.status = ATOM_STATUS_REJECTED
        rejected.append(atom)
    return rejected


def reject_conflicting_atom_candidates(
    reviews: list[AtomCandidateReview],
) -> list[NovelMemoryAtom]:
    """Reject only candidates that conflict with the accepted memory state."""
    return reject_atom_candidates([
        review.atom
        for review in reviews
        if review.conflict
    ])


async def sync_world_rule_doctrines(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    atoms: list[NovelMemoryAtom],
) -> list[ProjectDoctrine]:
    """Project the accepted world-rule atoms into the Doctrine layer.

    Doctrine is a read-optimized projection of hard world rules, not another
    model call. New versions deactivate the previous version for the same key.
    """
    projected: list[ProjectDoctrine] = []
    for atom in atoms:
        if atom.atom_type != "world_rule" or atom.status != ATOM_STATUS_ACCEPTED:
            continue
        existing = list((await db.scalars(
            select(ProjectDoctrine).where(
                ProjectDoctrine.project_id == project_id,
                ProjectDoctrine.branch_id == atom.branch_id,
                ProjectDoctrine.storyline_id == atom.storyline_id,
                ProjectDoctrine.doctrine_key == atom.memory_key,
            ).order_by(ProjectDoctrine.version.desc())
        )).all())
        latest = existing[0] if existing else None
        if latest and latest.is_active and latest.content == atom.statement:
            continue
        for item in existing:
            item.is_active = False
        doctrine = ProjectDoctrine(
            project_id=project_id,
            branch_id=atom.branch_id,
            storyline_id=atom.storyline_id,
            source_ref=atom.source_ref,
            source_chapter=atom.source_chapter,
            confidence=atom.confidence,
            version=(latest.version + 1) if latest else 1,
            valid_from_chapter=atom.valid_from_chapter,
            valid_to_chapter=atom.valid_to_chapter,
            authority=atom.authority,
            doctrine_key=atom.memory_key,
            doctrine_type="world_rule",
            content=atom.statement,
            data=atom.data or {},
            is_active=True,
        )
        db.add(doctrine)
        projected.append(doctrine)
    if projected:
        await db.flush()
    return projected
