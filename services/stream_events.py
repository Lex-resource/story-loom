"""流式事件的统一词表与发播助手 —— 表现层收口。

service 层不再直接拼事件名字符串和前端文案:事件名、来源与 extractor 各阶段
的提示文案都定义在这里,payload 形状与前端契约保持不变。改文案只动本文件。
"""

from __future__ import annotations

from services.stream_constants import STREAM_SOURCE_EXTRACTOR
from services.stream_manager import stream_manager

STREAM_EVENT_LOG = "log"
STREAM_EVENT_CHARACTER_BRANCH = "character_branch"

# extractor 各阶段的前端提示文案(key 是阶段名,不是给人看的 ID)。
EXTRACTOR_LOG_PHASES: dict[str, str] = {
    "startup": "分层记忆提取器启动：正在从章节正文提取人物状态、世界规则、伏笔和剧情线变化...",
    "analyzing": "设定提取分析中：正在通过大语言模型同步人物状态、伏笔回收及世界规则变动...",
    "writing": "正在写入并更新最新的人物经历与状态卡...",
}


async def broadcast_extractor_phase(project_id, phase: str) -> None:
    """以固定 payload 形状广播 extractor 阶段日志。未知阶段立即报错。"""
    message = EXTRACTOR_LOG_PHASES.get(phase)
    if not message:
        raise KeyError(f"Unknown extractor log phase: {phase!r}. Known: {sorted(EXTRACTOR_LOG_PHASES)}")
    await stream_manager.broadcast(
        str(project_id),
        STREAM_EVENT_LOG,
        {"source": STREAM_SOURCE_EXTRACTOR, "message": message},
    )
