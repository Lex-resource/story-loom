"""Helpers for constructing LLM prompt hint blocks.

Centralizes the ``\\n\\n【label】\\n{content}`` pattern duplicated across
planner.py, writer.py, and editor.py. Each helper returns "" when the
input is empty/falsy so callers can unconditionally pass results to
``safe_format`` without extra branching.
"""
import string
from agents.base import sanitize_untrusted_content


def hint_block(header: str, content: str, suffix: str = "") -> str:
    """Build a ``\\n\\n{header}\\n{content}{suffix}`` hint block.

    ``header`` is the full label string including any 【】 markers
    (e.g. ``"【用户实时干预指令 — 必须优先执行】"``). Returns empty string
    when ``content`` is falsy. Content is sanitized via
    ``sanitize_untrusted_content`` to prevent prompt injection. Optional
    ``suffix`` is appended verbatim (used for tail explanatory text such
    as the editor's decision guidance).
    """
    if not content:
        return ""
    body = f"\n\n{header}\n{sanitize_untrusted_content(content)}"
    if suffix:
        body += suffix
    return body


def intervention_hint(intervention: str) -> str:
    """Hint block for user real-time intervention (used by planner/writer/editor)."""
    return hint_block("【用户实时干预指令 — 必须优先执行】", intervention)


def vector_context_hint(vector_context: str) -> str:
    """Hint block for retrieved vector context (used by writer/editor)."""
    return hint_block("【相关背景补充】", vector_context)


def reference_style_hint(reference_style: str, label: str = "写作风格参考") -> str:
    """Hint block for reference style.

    ``label`` differs between planner (``"策划风格参考"``) and writer/editor
    (``"写作风格参考"``).
    """
    return hint_block(f"【{label}】", reference_style)


def validation_errors_hint(errors: str, suffix: str = "") -> str:
    """Hint block for validation errors with optional suffix explanation."""
    return hint_block("【关键】内容规则与安全校验错误提示：", errors, suffix=suffix)


def append_missing_hints(prompt_str: str, template: str, **hints) -> str:
    """Append hint values whose placeholder is missing from the template.

    Avoids duplicating the ``string.Formatter().parse()`` fallback logic
    previously inlined twice in planner.py. Only non-empty hint values are
    appended.
    """
    parsed_keys = {tup[1] for tup in string.Formatter().parse(template) if tup[1] is not None}
    for name, value in hints.items():
        if value and name not in parsed_keys:
            prompt_str += value
    return prompt_str
