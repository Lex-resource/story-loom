"""Event helpers for generation workers.

The generation pipeline should describe domain events (chunk, status, log,
warning) without knowing the exact websocket payload shape at every call site.
"""

from __future__ import annotations

from services.stream_manager import stream_manager


class GenerationEvents:
    def __init__(self, project_id: str):
        self.project_id = project_id

    async def chunk(
        self,
        agent: str,
        chapter_index: int,
        text: str,
        *,
        phase: str | None = None,
    ) -> None:
        data = {"agent": agent, "chapter_index": chapter_index, "text": text}
        if phase:
            data["phase"] = phase
        await stream_manager.broadcast(self.project_id, "chunk", data)

    async def status(self, step: str, chapter: int, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "status",
            {"step": step, "chapter": chapter, "message": message},
        )

    async def log(self, source: str, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "log",
            {"source": source, "message": message},
        )

    async def warning(self, chapter: int, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "warning",
            {"chapter": chapter, "message": message},
        )

    async def error(self, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "error",
            {"message": message},
        )

    async def validator_messages(self, result: dict, chapter: int) -> None:
        for info in result.get("infos", []):
            await self.log("校验器", f"[提示] {info}")
        for warn in result.get("warnings", []):
            await self.log("校验器", f"[警告] {warn}")
            await self.warning(chapter, warn)
