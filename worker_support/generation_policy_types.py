from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContentPair:
    draft_content: str | None
    edited_content: str | None

    @property
    def current_text(self) -> str:
        return self.edited_content or self.draft_content or ""


@dataclass
class GenerationStartState:
    start_step: str
    use_existing_outline: bool
    custom_prompt: str | None


@dataclass
class GenerationLoopState:
    draft_content: str | None
    edited_content: str | None
    rewrite_count: int
    max_rewrites: int
    decision: str
    validation_errors: str
    latest_validator_result: dict[str, Any] | None
    raw_issues: list[dict[str, Any]]
    skip_write_edit: bool
