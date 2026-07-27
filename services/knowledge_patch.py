"""Compatibility facade for knowledge patch models and application logic.

New production code should import from ``knowledge_patch_models``,
``knowledge_patch_handlers``, or ``knowledge_patch_service`` directly.
"""

from services.knowledge_patch_handlers import (  # noqa: F401
    PATCH_HANDLERS,
    apply_character,
    apply_foreshadowing,
    apply_patch,
    apply_plot_thread,
    apply_world_rule,
    register_patch_handler,
)
from services.knowledge_patch_models import (  # noqa: F401
    KnowledgePatch,
    KnowledgePatchSet,
    KnowledgePatchSummary,
    PatchCategory,
    PatchOperation,
)
from services.knowledge_patch_service import apply_knowledge_patches  # noqa: F401
