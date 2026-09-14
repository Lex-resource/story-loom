"""Event helpers for generation workers.

The generation pipeline should describe domain events (chunk, status, log,
warning) without knowing the exact websocket payload shape at every call site.
"""

from __future__ import annotations

from services.stream_manager import stream_manager


class GenerationEvents:
    def __init__(self, project_id: str, *, scope: dict | None = None):
        """``scope`` 为可选的域标记字典(如支线的 branch_id/scope),
        合并进每个事件 payload——主线不传,payload 形状不变。"""
        self.project_id = project_id
        self.scope = dict(scope or {})

    def _scoped(self, data: dict) -> dict:
        return {**self.scope, **data} if self.scope else data

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
        await stream_manager.broadcast(self.project_id, "chunk", self._scoped(data))

    async def status(self, step: str, chapter: int, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "status",
            self._scoped({"step": step, "chapter": chapter, "message": message}),
        )

    async def log(self, source: str, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "log",
            self._scoped({"source": source, "message": message}),
        )

    async def warning(self, chapter: int, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "warning",
            self._scoped({"chapter": chapter, "message": message}),
        )

    async def error(self, message: str) -> None:
        await stream_manager.broadcast(
            self.project_id,
            "error",
            self._scoped({"message": message}),
        )

    async def validator_messages(self, result: dict, chapter: int) -> None:
        for info in result.get("infos", []):
            await self.log("校验器", f"[提示] {info}")
        for warn in result.get("warnings", []):
            await self.log("校验器", f"[警告] {warn}")
            await self.warning(chapter, warn)
