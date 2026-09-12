"""Agent 名词汇(跨 models/services/agents/worker_support/routers 共用)。"""

# Canonical agent / pipeline node names.
# Used by: agents/pipeline.py, worker_support/*, services/*,
# routers/settings.py, frontend store.
AGENT_PLANNER = "planner"
AGENT_WRITER = "writer"
AGENT_EDITOR = "editor"
AGENT_VALIDATOR = "validator"
AGENT_EXTRACTOR = "extractor"
AGENT_CHARACTER_CARD = "character_card"
# 记忆整合不是流水线节点，只是 post-processing 里的辅助调用；
# 独立命名是为了 usage 统计里能区分整合成本，不与 extractor 混算。
AGENT_SCENE_CONSOLIDATOR = "scene_consolidator"

