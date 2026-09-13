"""build_chapter_handoff 的特征测试(森林 C3 收尾)。

用序列式 fake session 驱动真实查询顺序,把交接包输出逐字节冻结。
查询编排与纯装配(`_assemble_chapter_handoff`)的边界重构必须保持字节一致。

重新生成基线::

    HANDOFF_SNAPSHOT_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/services/test_chapter_handoff_characterization.py
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

from services.chapter_continuity import build_chapter_handoff

FIXTURE = Path(__file__).parent.parent / "fixtures" / "chapter_handoff_snapshot.json"
UPDATE = os.environ.get("HANDOFF_SNAPSHOT_UPDATE") == "1"

PROJECT = uuid.uuid4()


def _chapter_row():
    return SimpleNamespace(
        chapter_index=2,
        title="潮声",
        outline={
            "characters_present": ["林照", "周岑"],
            "end_state": "林照停在白塔门前。",
            "narrative_stage": "冲突升级",
            "open_questions": ["设备侧回执为何延迟"],
        },
        content="林照停在白塔门前,等待设备侧回执。" + "潮水声持续了一整夜。" * 20,
        edited_content=None,
        draft_content=None,
    )


def _atom_row(atom_type, statement, chapter=2, version=1):
    return SimpleNamespace(
        atom_type=atom_type,
        statement=statement,
        source_chapter=chapter,
        version=version,
        source_ref=f"chapter:{chapter}",
        memory_key=f"key:{statement[:8]}",
        authority="accepted",
        status="accepted",
        data={"rule_type": "countdown"} if atom_type == "world_rule" else {},
    )


def _scene_row():
    return SimpleNamespace(
        scope_type="plotline",
        scope_key="主线",
        current_state={"location": "白塔门前"},
        recent_changes=["取得潮汐记录"],
        open_questions=["设备侧回执为何延迟"],
        source_ref="chapter:2:scene",
        source_chapter=2,
    )


class _HandoffSession:
    """按 build_chapter_handoff 的查询顺序回放种子数据。"""

    def __init__(self, previous, atoms_current, atoms_evidence, scenes):
        self._previous = previous
        self._queue = [atoms_current, atoms_evidence, scenes]
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(("scalar", str(statement)))
        return self._previous

    async def scalars(self, statement):
        self.statements.append(("scalars", str(statement)))
        rows = self._queue.pop(0) if self._queue else []

        class _Rows:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Rows(rows)


def _distinguish(statement: str) -> str:
    if "novel_scene_blocks" in statement:
        return "scenes"
    if "atom_type IN" in statement:
        return "evidence"
    return "atoms"


async def _run(previous_ending=""):
    previous = _chapter_row()
    atoms = [
        _atom_row("character_state", "林照持有第九次潮汐记录副本"),
        _atom_row("foreshadowing", "白色灯塔的真正功能尚未确认"),
        _atom_row("world_rule", "潮汐记录必须当日登记"),
    ]
    session = _HandoffSession(previous, atoms, list(atoms), [_scene_row()])
    handoff = await build_chapter_handoff(
        session, PROJECT, 3, previous_ending=previous_ending
    )
    assert session.statements[0][0] == "scalar"
    order = [_distinguish(s) for kind, s in session.statements[1:]]
    assert order == ["evidence", "scenes"] or order == ["atoms", "evidence", "scenes"], order
    return handoff.to_dict()


def _frozen_output() -> dict:
    import asyncio

    return {
        "with_ending": asyncio.run(_run(previous_ending="林照停在白塔门前。")),
        "without_ending": asyncio.run(_run()),
    }


def test_chapter_handoff_output_matches_characterization_snapshot():
    current = json.dumps(_frozen_output(), ensure_ascii=False, sort_keys=True, indent=2)
    if UPDATE:
        FIXTURE.write_text(current + "\n", encoding="utf-8")
    assert FIXTURE.exists(), "缺少特征基线文件,请以 HANDOFF_SNAPSHOT_UPDATE=1 生成"
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert current == json.dumps(frozen, ensure_ascii=False, sort_keys=True, indent=2), (
        "build_chapter_handoff 输出漂移:重构必须保持字节级一致;"
        "若为有意变更,先更新 fixtures 并在提交说明中给出理由"
    )
