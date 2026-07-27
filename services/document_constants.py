"""Living-doc document type constants."""

ALL_DOC_TYPES: tuple[str, ...] = (
    "world_state",
    "character_state",
    "foreshadowing",
    "plot_threads",
    "global_outline",
    "act_outline",
)

KNOWLEDGE_DOC_TYPES: tuple[str, ...] = (
    "world_state",
    "character_state",
    "foreshadowing",
    "plot_threads",
)

OUTLINE_DOC_TYPES: tuple[str, ...] = ("global_outline", "act_outline")

DOC_TYPE_WORLD_STATE: str = "world_state"
DOC_TYPE_CHARACTER_STATE: str = "character_state"
DOC_TYPE_FORESHADOWING: str = "foreshadowing"
DOC_TYPE_PLOT_THREADS: str = "plot_threads"
DOC_TYPE_GLOBAL_OUTLINE: str = "global_outline"
DOC_TYPE_ACT_OUTLINE: str = "act_outline"
