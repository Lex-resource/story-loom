"""Compatibility facade for knowledge graph/tree/timeline builders."""

from services.knowledge_character_graph import (
    build_character_graph,
    character_group_for,
)
from services.knowledge_foreshadowing_timeline import build_foreshadowing_timeline
from services.knowledge_plot_tracks import build_plot_tracks
from services.knowledge_world_rules import (
    build_world_rules_tree,
    world_rule_tag_for,
)
