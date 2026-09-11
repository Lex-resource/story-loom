"""Serialization and prompt projections for chapter handoff data."""

from __future__ import annotations

import json
from typing import Any

from services.context_compaction import compact_items, compact_json, compact_text


class ChapterHandoffFormattingMixin:
    """Keep handoff rendering separate from database-backed handoff assembly."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_chapter": self.previous_chapter,
            "previous_title": self.previous_title,
            "exact_ending": self.exact_ending,
            "end_scene": self.end_scene,
            "characters_present": self.characters_present,
            "inherited_state": self.inherited_state,
            "state_changes": self.state_changes,
            "completed_event_ledger": self.completed_event_ledger,
            "previous_terminal_state": self.previous_terminal_state,
            "open_questions": self.open_questions,
            "foreshadowing": self.foreshadowing,
            "next_hook": self.next_hook,
            "item_state_ledger": self.item_state_ledger,
            "evidence_state_ledger": self.evidence_state_ledger,
            "evidence_boundaries": self.evidence_boundaries,
            "unknown_boundary": self.unknown_boundary,
            "sources": self.sources,
        }

    def to_prompt(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    def to_compact_prompt(self, max_chars: int = 9000) -> str:
        """Render the production handoff projection, with research overrides."""
        from services.version_surface import NO_OVERRIDE, research_override

        override = research_override("handoff_compact_prompt", self, max_chars)
        if override is not NO_OVERRIDE:
            return override
        return self._to_v30_compact_prompt(max_chars)

    def _to_v10_compact_prompt(self, max_chars: int = 9000) -> str:
        compact_evidence = [
            {
                key: compact_text(value, 700) if isinstance(value, str) else value
                for key, value in item.items()
                if key not in {"source_ref"}
            }
            for item in self.evidence_state_ledger
        ]
        compact_items_ledger = [
            {
                key: compact_text(value, 700) if isinstance(value, str) else value
                for key, value in item.items()
                if key not in {"transitions", "source_ref"}
            }
            for item in self.item_state_ledger
        ]
        payload = {
            "previous_chapter": self.previous_chapter,
            "previous_title": self.previous_title,
            "exact_ending": compact_text(self.exact_ending, 1800, tail_chars=900),
            "end_scene": json.loads(compact_json(self.end_scene, 1400, label="end_scene") or "{}"),
            "characters_present": compact_items(self.characters_present, max_items=12, item_chars=300, keep="head"),
            "inherited_state": compact_items(self.inherited_state, max_items=20, item_chars=650, keep="tail"),
            "state_changes": self.state_changes[-8:],
            "completed_event_ledger": self.completed_event_ledger[-8:],
            "previous_terminal_state": self.previous_terminal_state,
            "open_questions": self.open_questions[-8:],
            "foreshadowing": self.foreshadowing[-8:],
            "next_hook": self.next_hook,
            "item_state_ledger": compact_items(compact_items_ledger, max_items=16, item_chars=700),
            "evidence_state_ledger": compact_items(compact_evidence, max_items=24, item_chars=700),
            "evidence_boundaries": compact_items(self.evidence_boundaries, max_items=8, item_chars=500, keep="head"),
            "unknown_boundary": compact_items(self.unknown_boundary, max_items=8, item_chars=500, keep="head"),
        }

        def render(value: dict[str, Any]) -> str:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

        rendered = render(payload)
        if len(rendered) <= max_chars:
            return rendered
        payload["exact_ending"] = compact_text(self.exact_ending, 900, tail_chars=450)
        payload["inherited_state"] = payload["inherited_state"][:20]
        payload["state_changes"] = compact_items(self.state_changes, max_items=4, item_chars=450)
        payload["open_questions"] = compact_items(self.open_questions, max_items=4, item_chars=450)
        payload["foreshadowing"] = compact_items(self.foreshadowing, max_items=4, item_chars=450)
        payload["item_state_ledger"] = payload["item_state_ledger"][:16]
        payload["evidence_state_ledger"] = payload["evidence_state_ledger"][:16]
        rendered = render(payload)
        if len(rendered) <= max_chars:
            return rendered
        compact_payload = {
            "previous_chapter": self.previous_chapter,
            "previous_title": self.previous_title,
            "exact_ending": compact_text(self.exact_ending, 600, tail_chars=300),
            "end_scene": payload["end_scene"],
            "characters_present": payload["characters_present"][:12],
            "inherited_state": payload["inherited_state"][:20],
            "next_hook": compact_text(self.next_hook, 500),
            "item_state_ledger": payload["item_state_ledger"],
            "evidence_state_ledger": self.evidence_state_ledger,
            "evidence_boundaries": payload["evidence_boundaries"][:4],
            "unknown_boundary": payload["unknown_boundary"][:4],
        }
        compact_payload["evidence_state_ledger"] = payload["evidence_state_ledger"][:12]
        return compact_json(compact_payload, max_chars, label="chapter_handoff")

    def _to_v30_compact_prompt(self, max_chars: int = 3000) -> str:
        def compact_record(
            item: dict[str, Any],
            fields: tuple[str, ...],
            text_fields: tuple[str, ...],
            item_chars: int,
        ) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for field in fields:
                value = item.get(field)
                if value in (None, "", [], {}):
                    continue
                result[field] = compact_text(value, item_chars) if field in text_fields else value
            return result

        item_states = [
            compact_record(
                item,
                ("memory_key", "name", "current_statement", "current_state", "source_chapter", "authority"),
                ("memory_key", "name", "current_statement", "current_state", "authority"),
                260,
            )
            for item in self.item_state_ledger
        ]
        evidence_states = [
            compact_record(
                item,
                ("evidence_kind", "memory_key", "subject", "proposition", "status", "authority", "source_chapter"),
                ("evidence_kind", "memory_key", "subject", "proposition", "status", "authority"),
                280,
            )
            for item in self.evidence_state_ledger
        ]
        payload: dict[str, Any] = {
            "previous_chapter": self.previous_chapter,
            "previous_title": compact_text(self.previous_title, 120),
            "exact_ending": compact_text(self.exact_ending, 800, tail_chars=500),
            "end_scene": json.loads(compact_json(self.end_scene, 550, label="end_scene") or "{}"),
            "characters_present": compact_items(self.characters_present, max_items=8, item_chars=180, keep="head"),
            "inherited_state": compact_items(self.inherited_state, max_items=10, item_chars=320, keep="tail"),
            "state_changes": compact_items(self.state_changes, max_items=4, item_chars=240, keep="tail"),
            "completed_event_ledger": compact_items(self.completed_event_ledger, max_items=8, item_chars=360, keep="tail"),
            "previous_terminal_state": self.previous_terminal_state,
            "open_questions": compact_items(self.open_questions, max_items=4, item_chars=240, keep="tail"),
            "foreshadowing": compact_items(self.foreshadowing, max_items=4, item_chars=240, keep="tail"),
            "next_hook": compact_text(self.next_hook, 420),
            "item_states": item_states[-8:],
            "evidence_states": evidence_states[-8:],
            "unknown_boundary": compact_items(self.unknown_boundary, max_items=6, item_chars=240, keep="head"),
        }

        def render(value: dict[str, Any]) -> str:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

        rendered = render(payload)
        if len(rendered) <= max_chars:
            return rendered
        payload["exact_ending"] = compact_text(self.exact_ending, 600, tail_chars=360)
        payload["end_scene"] = json.loads(compact_json(self.end_scene, 360, label="end_scene") or "{}")
        payload["characters_present"] = compact_items(self.characters_present, max_items=6, item_chars=140, keep="head")
        payload["inherited_state"] = compact_items(self.inherited_state, max_items=8, item_chars=230, keep="tail")
        payload["state_changes"] = compact_items(self.state_changes, max_items=2, item_chars=180, keep="tail")
        payload["completed_event_ledger"] = payload["completed_event_ledger"][:5]
        payload["open_questions"] = compact_items(self.open_questions, max_items=2, item_chars=180, keep="tail")
        payload["foreshadowing"] = compact_items(self.foreshadowing, max_items=2, item_chars=180, keep="tail")
        payload["next_hook"] = compact_text(self.next_hook, 300)
        payload["item_states"] = item_states[-6:]
        payload["evidence_states"] = evidence_states[-6:]
        payload["unknown_boundary"] = compact_items(self.unknown_boundary, max_items=4, item_chars=180, keep="head")
        rendered = render(payload)
        if len(rendered) <= max_chars:
            return rendered
        payload["state_changes"] = []
        payload["completed_event_ledger"] = payload["completed_event_ledger"][:4]
        payload["open_questions"] = []
        payload["foreshadowing"] = []
        payload["characters_present"] = payload["characters_present"][:4]
        payload["inherited_state"] = payload["inherited_state"][:6]
        payload["item_states"] = payload["item_states"][:4]
        payload["evidence_states"] = payload["evidence_states"][:4]
        return compact_json(payload, max_chars, label="chapter_handoff_v30")

