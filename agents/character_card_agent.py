"""AI generation of initial, schema-validated character cards."""

from __future__ import annotations

import json
from typing import Any

from agents.base import (
    AgentBase,
    UNTRUSTED_CONTENT_SYSTEM_REMINDER,
    safe_format,
    sanitize_untrusted_content,
)
from agents.constants import CHARACTER_CARD_TEMPERATURE, PROMPT_CHARACTER_GENERATE_CARDS
from services.character_types import CharacterCardGenerationResponse


class CharacterCardAgent(AgentBase):
    """Generate cards only; persistence and authority remain in the service layer."""

    async def generate_cards(
        self,
        *,
        project_context: dict[str, Any],
        character_hints: list[dict[str, Any]],
        user_hints: str,
        novel_format: str,
    ) -> dict[str, Any]:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_CHARACTER_GENERATE_CARDS,
            category=novel_format,
        )
        user_prompt = safe_format(
            user_tmpl,
            project_context=sanitize_untrusted_content(
                json.dumps(project_context, ensure_ascii=False, indent=2)
            ),
            character_hints=sanitize_untrusted_content(
                json.dumps(character_hints, ensure_ascii=False, indent=2)
            ),
            user_hints=sanitize_untrusted_content(user_hints or "（无）"),
        )
        return await self.call_llm_json(
            system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER,
            user_prompt,
            temperature=CHARACTER_CARD_TEMPERATURE,
            response_schema=CharacterCardGenerationResponse,
        )
