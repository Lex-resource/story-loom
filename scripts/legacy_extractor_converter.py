from __future__ import annotations

import uuid
from typing import Any

from services.knowledge_patch_models import KnowledgePatch, KnowledgePatchSet, PatchOperation


def old_extractor_result_to_patches(extract_result: dict[str, Any], chapter_index: int | None = None) -> KnowledgePatchSet:
    patches: list[KnowledgePatch] = []
    for update in extract_result.get("character_updates", []):
        name = (update.get("name") or "").strip()
        changes = update.get("changes") or {}
        if name and changes:
            patches.append(KnowledgePatch(category="character_state", operation="merge", name=name, data={"attributes": changes}))

    for update in extract_result.get("world_updates", []):
        name = (update.get("entity") or "").strip() or "全局通用规则"
        content = (update.get("content") or "").strip()
        if content:
            patches.append(KnowledgePatch(category="world_state", operation="append_progress", name=name, data={"rule_type": update.get("type", ""), "body": content}))

    for update in extract_result.get("foreshadowing_updates", []):
        action = (update.get("action") or "upsert").strip()
        name = (update.get("id") or "").strip()
        if name.startswith("fs_"):
            name = name[3:]
        if action == "plant" or not name:
            operation: PatchOperation = "upsert"
            name = uuid.uuid4().hex[:8]
        elif action == "resolve":
            operation = "resolve"
        elif action == "cancel":
            operation = "cancel"
        else:
            operation = "merge"
        patches.append(KnowledgePatch(category="foreshadowing", operation=operation, name=name, data={
            "description": update.get("description", ""),
            "importance": update.get("importance", "medium"),
            "chapter": update.get("chapter") or chapter_index or 1,
        }))

    for update in extract_result.get("plot_thread_updates", []):
        name = (update.get("thread") or "").strip()
        progress = (update.get("progress") or "").strip()
        if name and progress:
            patches.append(KnowledgePatch(category="plot_threads", operation="append_progress", name=name, data={"progress": progress, "next_step": update.get("next_step", "")}))

    return KnowledgePatchSet(
        patches=patches,
        vector_items=extract_result.get("vector_items", []) or [],
        raw_issues=extract_result.get("raw_issues", []) or [],
    )
