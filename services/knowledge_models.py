"""Compatibility facade for structured knowledge model imports.

New code should import from the cohesive modules directly:
- services.knowledge_types
- services.knowledge_markdown
- services.knowledge_settings
"""

from services.knowledge_markdown import knowledge_from_markdown, knowledge_to_markdown
from services.knowledge_settings import (
    as_foreshadowing,
    format_markdown_from_knowledge,
    knowledge_from_settings_doc,
    settings_doc_payload_from_knowledge,
)
from services.knowledge_types import (
    CATEGORY_TO_DOC_TYPE,
    DOC_TYPE_TO_CATEGORY,
    CharacterKnowledge,
    ForeshadowingKnowledge,
    KnowledgeBase,
    KnowledgeDocType,
    KnowledgeModel,
    PlotThreadKnowledge,
    WorldRuleKnowledge,
)

_as_foreshadowing = as_foreshadowing
_format_markdown_from_knowledge = format_markdown_from_knowledge

__all__ = [
    "KnowledgeDocType",
    "KnowledgeBase",
    "CharacterKnowledge",
    "WorldRuleKnowledge",
    "ForeshadowingKnowledge",
    "PlotThreadKnowledge",
    "KnowledgeModel",
    "DOC_TYPE_TO_CATEGORY",
    "CATEGORY_TO_DOC_TYPE",
    "knowledge_to_markdown",
    "knowledge_from_markdown",
    "knowledge_from_settings_doc",
    "settings_doc_payload_from_knowledge",
    "format_markdown_from_knowledge",
    "as_foreshadowing",
    "_format_markdown_from_knowledge",
    "_as_foreshadowing",
]
