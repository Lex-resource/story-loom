"""Writer 执行简报的特征测试(森林 C3 断环点)。

`writer_execution_brief` 是纯函数(handoff + contract → 简报文本),此前输出
无任何直接锁定。拆分这 190 行装配逻辑前,先在固定输入上把两种 novel_format
分支的输出逐字节冻结。

重新生成基线::

    BRIEF_SNAPSHOT_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/services/test_execution_brief_characterization.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from services.chapter_continuity import writer_execution_brief
from services.continuity_contract import build_chapter_contract

FIXTURE = Path(__file__).parent.parent / "fixtures" / "execution_brief_snapshot.json"
UPDATE = os.environ.get("BRIEF_SNAPSHOT_UPDATE") == "1"

OUTLINE = {
    "chapter_index": 3,
    "title": "回执",
    "required_events": ["核对第九次潮汐登记的来源字段", "守军对塔内异常起疑"],
    "state_changes": ["林照持有第九次潮汐记录副本"],
    "foreshadowing_actions": ["推进白色灯塔功能悬念"],
    "new_stage_delta": ["调查从被动接收转向主动核对"],
    "end_state": "林照带着记录副本离开码头,来源仍未确认。",
    "primary_action": {"action": "核对记录来源", "actor": "林照"},
    "character_turn": {"actor": "林照", "want": "确认记录真实来源", "blocked_by": "守军巡逻"},
    "unknown_boundary": ["白色灯塔的真正功能未知"],
    "unique_action_ledger": [{"action": "调阅潮汐登记", "chapter": 2}],
    "recording_action_rules": {"mode": "ledger_only_physical_artifacts"},
    "interpretation_boundary_rules": {"rule": "先写观察,再写保留不确定性的猜测。"},
    "end_state_boundary": {"authority": "terminal_chapter_state"},
    "continuity_from_previous": ["承接白塔门前的等待状态"],
}

HANDOFF_DICT = {
    "previous_chapter": 2,
    "previous_title": "潮声",
    "exact_ending": "林照停在白塔门前,等待设备侧回执。",
    "end_scene": {"location": "白塔门前", "time": "退潮后"},
    "characters_present": ["林照", "周岑"],
    "inherited_state": [{"memory_key": "access:tower", "current_statement": "门禁授权已到期"}],
    "state_changes": ["林照取得第九次潮汐记录副本"],
    "completed_event_ledger": [{"event": "调阅潮汐登记", "source_chapter": 2}],
    "open_questions": ["设备侧回执为何延迟"],
    "next_hook": "退潮后的第二次核对窗口",
    "unknown_boundary": ["上一章记录存在缺页"],
    "item_state_ledger": [{"item": "潮汐记录副本", "holder": "林照"}],
}

CONTRACT = build_chapter_contract(OUTLINE, HANDOFF_DICT)


def _frozen_output() -> dict:
    return {
        "long_form": writer_execution_brief(HANDOFF_DICT, CONTRACT, max_chars=4200),
        "short_form": writer_execution_brief(
            HANDOFF_DICT, CONTRACT, max_chars=2600, novel_format="zhihu_short"
        ),
    }


def test_execution_brief_output_matches_characterization_snapshot():
    current = json.dumps(_frozen_output(), ensure_ascii=False, sort_keys=True, indent=2)
    if UPDATE:
        FIXTURE.write_text(current + "\n", encoding="utf-8")
    assert FIXTURE.exists(), "缺少特征基线文件,请以 BRIEF_SNAPSHOT_UPDATE=1 生成"
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert current == json.dumps(frozen, ensure_ascii=False, sort_keys=True, indent=2), (
        "writer_execution_brief 输出漂移:拆分重构必须保持字节级一致;"
        "若为有意变更,先更新 fixtures 并在提交说明中给出理由"
    )
