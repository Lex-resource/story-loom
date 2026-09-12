"""契约构建器的特征测试(森林 C4 断环点)。

`build_chapter_contract` 的输出此前没有任何直接锁定——V43 快照只锁
`contract_prompt` 的渲染结果。要把 237 行的构建函数拆分,先在固定输入上
把当前输出逐字节冻结;此后任何重构必须让这份 JSON 保持不变。

重新生成基线(只应伴随有意的契约结构变更)::

    CONTRACT_SNAPSHOT_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/services/test_contract_builder_characterization.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from services.chapter_continuity import ChapterHandoff
from services.continuity_contract import build_chapter_contract, build_dramatic_turn_projection

FIXTURE = Path(__file__).parent.parent / "fixtures" / "contract_builder_snapshot.json"
UPDATE = os.environ.get("CONTRACT_SNAPSHOT_UPDATE") == "1"

OUTLINE = {
    "volume_title": "第三卷 潮汐之下",
    "acts": [
        {"act": 1, "title": "码头疑云", "chapters": [7, 8, 9, 10]},
        {"act": 2, "title": "白塔试炼", "chapters": [11, 12, 13]},
    ],
    "chapters": [
        {
            "chapter_index": 3,
            "title": "回执",
            "summary": "林照取得第九次潮汐记录副本，守军对塔内异常起疑。",
            "narrative_stage": "冲突升级",
            "plotline": "主线",
            "characters_involved": ["林照", "周岑"],
            "foreshadowing": ["白色灯塔的真正功能"],
            "key_events": ["取得潮汐记录", "守军起疑"],
        },
        {
            "chapter_index": 4,
            "title": "涨潮",
            "summary": "潮汐异常提前，林照必须赶在记录失效前核对来源。",
            "narrative_stage": "高潮",
            "plotline": "主线",
            "characters_involved": ["林照"],
            "foreshadowing": ["白色灯塔的真正功能"],
            "key_events": ["核对记录来源"],
        },
    ],
    "world_rules": [
        {"name": "潮汐登记", "rule": "每次潮汐记录必须在白塔登记，否则失效。"},
    ],
    "foreshadowing": [
        {"name": "白色灯塔的真正功能", "planted_chapter": 2, "expected_payoff": 6},
    ],
    "entities": [
        {"type": "character", "name": "林照", "description": "档案员，追查潮汐异常。"},
        {"type": "setting", "name": "白塔", "description": "海岸线上的登记塔。"},
    ],
}

HANDOFF = ChapterHandoff(
    previous_chapter=2,
    previous_title="潮声",
    exact_ending="林照停在白塔门前，等待设备侧回执。",
    end_scene={"location": "白塔门前", "time": "退潮后"},
    characters_present=["林照", "周岑"],
    inherited_state=[{"memory_key": "access:tower", "current_statement": "门禁授权已到期"}],
    state_changes=["林照取得第九次潮汐记录副本"],
    completed_event_ledger=[{"event": "调阅潮汐登记", "source_chapter": 2}],
).to_dict()


def _frozen_output() -> dict:
    contract = build_chapter_contract(OUTLINE, HANDOFF)
    return {
        "contract": contract,
        "dramatic_turn": build_dramatic_turn_projection(contract),
    }


def test_contract_builder_output_matches_characterization_snapshot():
    current = json.dumps(_frozen_output(), ensure_ascii=False, sort_keys=True, indent=2)
    if UPDATE:
        FIXTURE.write_text(current + "\n", encoding="utf-8")
    assert FIXTURE.exists(), "缺少特征基线文件,请以 CONTRACT_SNAPSHOT_UPDATE=1 生成"
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert current == json.dumps(frozen, ensure_ascii=False, sort_keys=True, indent=2), (
        "build_chapter_contract 输出漂移:拆分重构必须保持字节级一致;"
        "若为有意变更,先更新 fixtures 并在提交说明中给出理由"
    )
