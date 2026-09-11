"""短篇(知乎体)工作流的提示词表面。

这是短篇的**第一套自己的表面**。在此之前短篇复用长篇 A28/V43 的连续性栈,实测
五个 agent 的 system prompt 平均 73% 是长篇材料(Writer 达 80%),其中三类规则与
短篇形式直接对抗:

* `V36 记录动作承诺` —— 禁止为记录信息新增笔记本/纸张/笔/便签等,除非 `item_state_ledger`
  已登记。短篇没有物品账本,等于全面禁纸笔。这条规则长在长篇科技悬疑实验里。
* `V42/V43 权威锁定与受限假设` —— 模糊署名/相似身份只能保持为待核对线索,不可写成
  身份、来源、因果结论;不可逆行动不得建立在未确认假设上。而短篇最后一节的真相揭露
  和不可逆结局**正是要做这件被禁止的事**。
* `V37 观察解释三层` —— 界面/设备/回执语汇。多数短篇题材没有设备回执。

外加 `V43 本章只设置一个主叙事增量` + `最多保留一个核心未决问题`:三节短篇每节要
钩子、升级、转折,这条直接封顶反转密度。

短篇栈因此不是「长篇栈的裁剪」,而是换了约束对象:长篇约束**跨章事实不漂移**,
短篇约束**承诺被兑现、反转公平、情绪落点到位、人称不越权**。

长篇路径完全不经过本模块(`workflow_surface.strategy_for` 对 `frozen_v43` 直接让路)。
"""
from __future__ import annotations

from typing import Any

from services.validation_constants import RETRYABLE_CATEGORIES
from services.workflow_surface import STRATEGY_SHORT_FORM, register


# ---------------------------------------------------------------------------
# 生成 hint 栈
# ---------------------------------------------------------------------------
# 每个 agent 一段,目标量级 300-500 字符(长篇同位栈为 1391-1877)。短篇作者自己写的
# 模板只有 475-1278 字符,注入材料不该再压过它。

_SHORT_HINTS: dict[str, str] = {
    "planner": (
        "\n\n【短篇分节要求】\n"
        "每节都要有钩子、实质推进和情绪落点,不要把一节压成单一增量。反转必须公平:"
        "本节反转所需的线索,必须在此前分节已出现或在本节内先行给出,不能凭空掉落。"
        "维护开篇承诺台账 —— 开篇许诺的悬念、爽点或情绪爆点,要明确安排在哪一节兑现;"
        "最后一节必须收束核心冲突并留下余味。全篇人称统一,不要规划需要越权视角才能成立的场面。"
        "不要长篇式支线、履历铺陈或背景堆叠。"
    ),
    "writer": (
        "\n\n【短篇正文要求】\n"
        "以对话和行动推进场景,不写背景讲解和总结腔。每节结尾留下情绪落点或追读钩子。"
        "反转要让读者可回看:落地前确认铺垫已在前文出现过。"
        "全篇人称统一;第一人称不得越权描写他人内心或不在场的事件。\n"
        "**结局许可**:这是短篇,最后一节可以、也应该把线索收成确定结论,做不可逆的揭露、"
        "对决或情绪爆发。不要为求稳把结局写成「也许/待核实」的悬置 —— 悬置不是短篇的结尾。"
    ),
    "editor": (
        "\n\n【短篇审阅要求】\n"
        "优先修文风、句式和节奏;保护笑点节奏与情绪转折,不要把口语幽默改端。"
        "不得因为篇幅短、事件少或缺少铺垫而打回重写 —— 那是短篇的形式,不是缺陷。"
        "只有人称越权、与前文分节的事实冲突、开篇承诺被违背,或反转完全没有铺垫,才构成硬问题;"
        "其余一律在 edited_content 内直接改好。"
    ),
    "validator": (
        "\n\n【短篇校验边界】\n"
        "只有四类构成 block:人称越权描写、与前文分节的事实冲突、开篇承诺被违背、"
        "关键反转在全文中找不到任何铺垫。\n"
        "节奏、密度、文风、爽点不足一律 warning,不得单独触发重写。"
        "特别注意:最后一节把前文线索收成确定的身份、动机、因果或结局,是短篇的正常收束,"
        "**不是**无证据升级,不得据此判冲突。"
    ),
    "extractor": (
        "\n\n【短篇记忆沉淀】\n"
        "短篇只需沉淀跨节续写真正要用的东西:人物当前状态与关系、已经用过的反转"
        "(供后续分节避免重复)、已兑现与未兑现的开篇承诺、已回收的伏笔。"
        "不要为短篇制造长篇式的候选/权威分级膨胀,也不要把一次性场景细节沉淀成长期事实。"
    ),
}


@register(STRATEGY_SHORT_FORM, "generation_hints")
def short_generation_hints(agent_type: str) -> str:
    return _SHORT_HINTS.get(agent_type, _SHORT_HINTS["writer"])


# ---------------------------------------------------------------------------
# Planner 章节契约输出要求
# ---------------------------------------------------------------------------


@register(STRATEGY_SHORT_FORM, "chapter_contract_output_requirements")
def short_chapter_contract_output_requirements() -> str:
    """与短篇 planner 自己的 schema 一致的字段要求。

    长篇版本无条件要求 `required_events`、`uncertain_events`、`continuity_from_previous`、
    `state_changes`、`foreshadowing_actions`、`forbidden_deviations`、`unknown_boundary`、
    `continuity_contract` 八个字段 —— 短篇 planner 模板的 schema 里**一个都没有**,
    却同时被告知「严格匹配以下结构」。这条自相矛盾的指令是短篇契约字段大面积为空的
    直接原因,而空字段又让 `writer_execution_brief` 落回长篇兜底。这里把要求改回
    短篇 schema 实际拥有的字段。
    """
    return (
        "\n\n【短篇分节输出要求】\n"
        "输出 summary、key_events、emotional_arc、beats、character_goals、"
        "related_foreshadowing 和 narrative_stage。"
        "emotional_arc 写本节情绪起落;beats 是 3-6 个有序场景节拍;"
        "character_goals 给出场角色的目标、阻力和本节结束时的状态推进。"
        "key_events 只写本节真正发生的事,不要重复前文已成立的状态。"
    )


# ---------------------------------------------------------------------------
# Editor 策略
# ---------------------------------------------------------------------------


@register(STRATEGY_SHORT_FORM, "editor_policy")
def short_editor_policy() -> dict[str, object]:
    """短篇 Editor 策略。

    长篇版本的 `review_strategy` 末句要求 evaluations 追加 `chapter_continuity` 和
    `foreshadowing_payoff`(跨章关切),而短篇的响应 schema 只有五维 —— 短篇 Editor
    因此长期收到自相矛盾的指令,多产的两维也没有任何消费者。短篇换成自己的两维:
    `hook_strength` 与 `emotional_landing`,都是**逐节可评**的短篇关切。
    """
    return {
        "review_strategy": (
            "\n\n【短篇低重试审阅策略】\n"
            "只有人称越权、与前文分节的事实冲突、开篇承诺被违背、关键反转毫无铺垫,"
            "或正文严重偏离本节大纲,才允许 decision=rewrite。"
            "篇幅短、事件少、节奏偏快都不是重写理由,必须直接在 edited_content 中改好。\n"
            "【短篇七维评分硬约束(覆盖模板中的旧评分说明)】\n"
            "evaluations 必须显式输出且只接受以下七个字段:"
            "plot_progression、character_portrayal、world_consistency、writing_quality、"
            "logical_coherence、hook_strength、emotional_landing。"
            "每个字段都是 {score: 1-10 的整数, reason: 有证据的中文说明}。"
            "hook_strength 评本节钩子与追读力,emotional_landing 评本节情绪落点是否到位,"
            "两者都必须引用本节正文的具体依据。\n"
            "即使模板前文写着五维,也必须按本段输出七维;禁止省略后两项,"
            "禁止输出 chapter_continuity 或 foreshadowing_payoff(那是长篇维度)。"
        ),
        "project_outline": False,
        "long_form_quality_contract": False,
        "research_response_schema": False,
    }


# ---------------------------------------------------------------------------
# 质量维度
# ---------------------------------------------------------------------------
# 长篇是「五维手艺 + 两维跨章」(chapter_continuity / foreshadowing_payoff);
# 短篇对称地是「五维手艺 + 两维分节」(hook_strength / emotional_landing)。
# 两者都在 7 项齐全时 complete=true,于是短篇终于有了可比较的质量指标。
#
# 完结全文审校(`services/short_story_review.py`)另有一套**全文级**五维
# (promise_payoff / foreshadowing_fairness / emotional_arc / information_density /
# ending_closure) —— 那是全文才有意义的结构维度,不下放到逐节评分。

SHORT_QUALITY_DIMENSIONS: tuple[str, ...] = (
    "plot_progression",
    "character_portrayal",
    "world_consistency",
    "writing_quality",
    "logical_coherence",
    "hook_strength",
    "emotional_landing",
)


@register(STRATEGY_SHORT_FORM, "quality_dimensions")
def short_quality_dimensions() -> tuple[str, ...]:
    return SHORT_QUALITY_DIMENSIONS


@register(STRATEGY_SHORT_FORM, "quality_gate_minimums")
def short_quality_gate_minimums() -> dict[str, float]:
    """短篇的门槛维度。长篇卡跨章衔接与伏笔兑现,短篇卡钩子与情绪落点。"""
    return {"hook_strength": 8.5, "emotional_landing": 8.5}


# ---------------------------------------------------------------------------
# Writer 执行简报
# ---------------------------------------------------------------------------


@register(STRATEGY_SHORT_FORM, "validator_extra_requirements")
def short_validator_extra_requirements() -> str:
    """短篇 Validator 的额外硬规则。

    长篇版本把「本章单章大纲中的 required_changes、end_state、beats」列为本章允许落地的
    新事实来源 —— 短篇 planner 的 schema 里没有前两个字段，于是这条豁免对短篇实际失效，
    Validator 会因为「角色卡尚未记录」而误判本节合理的新事实。这里换成短篇真实存在的字段。
    """
    return (
        "\n【短篇校验器额外要求】角色事实、地点、能力、关系和伤势属于硬规则；"
        "正文与前文分节已确认的事实冲突时，输出 severity=block，并在 evidence 与 "
        "conflicts_with 中分别引用正文证据和冲突事实。\n"
        "本节大纲中的 key_events、beats 和 emotional_arc 是本节允许落地的新事实来源："
        "正文按大纲给出了合理触发和过渡时，不得仅因为角色卡尚未记录该事实就判冲突。"
    )


@register(STRATEGY_SHORT_FORM, "validator_trailing_hint")
def short_validator_trailing_hint() -> str:
    """短篇没有物品账本，跨章物品账本提示对它是纯噪声。"""
    return ""


@register(STRATEGY_SHORT_FORM, "retry_categories")
def short_retry_categories() -> frozenset[str]:
    """短篇哪些类别的阻断级问题该退回 Writer 重写 —— 长篇基线加两类。

    短篇 validator 模板要求 LLM 用 `logic|consistency|pacing|payoff|viewpoint`
    (`prompts/validation/zhihu_short_validation.json`)，而短篇表面（本文件的 validator
    hint）宣布只有四类构成 block：人称越权、与前文分节的事实冲突、开篇承诺被违背、
    关键反转毫无铺垫。对上长篇词表后，`consistency` 与 `logic` 能正常触发重写，
    **`viewpoint` 和 `payoff` 一个都不在**，于是这两类最致命的短篇缺陷反而走
    `force_save_validator_result` 直接落盘并被标成 `passed=True`。

    两类都退回 Writer 重写，不引入「退给 Editor 局部修复」的第三档：那要动
    `worker_support/generation_validation_flow.py` 的编排，会碰 20 条 golden trace；
    而短篇只 3 节、`max_rewrites_override=2`，重写成本本来就低。

    `pacing` 刻意**不**加进来 —— 短篇表面明说节奏、密度、文风一律 warning，不得单独
    触发重写；它由 `worker_support/validation.py` 的 story_issue 分流收成观察项。
    """
    return RETRYABLE_CATEGORIES | {"viewpoint", "payoff"}


_SUPPRESS_HANDOFF_AND_CONTRACT = frozenset({"editor", "validator", "extractor"})


@register(STRATEGY_SHORT_FORM, "agent_context_policy")
def short_agent_context_policy(agent_type: str) -> dict[str, bool]:
    """短篇的 Editor/Validator/Extractor 不收交接包与章节契约的原始副本。

    Writer 早就不收了（`writer_context_policy`，V35 起归 execution brief 所有），这三家
    一直在收。两份 payload 的内容是跨章物品/证据账本：`item_states`、`evidence_states`、
    `completed_event_ledger`、`previous_terminal_state`、`state_changes`、`new_stage_delta`、
    `end_state_boundary` —— 短篇 planner 全都不产出，投影出来是空壳配长篇语汇，而
    Editor 与 Validator 恰好是决定要不要重写的两个角色，噪声直接转成误判。

    `build_chapter_contract`（services/continuity_contract.py）本身没有格式轴，仍按长篇形状
    生成纸张禁令、`countdown_monotonic`、`post_closure_window` 这些规则。本表面做完后它在
    短篇路径上不再有消费者：Writer 侧的简报早已被 `execution_brief_boilerplate` 裁掉那四块
    兜底，这三家的原始副本到这里被清空。改契约生成本身会碰 V43 黄金快照锁定的契约规范化
    结果，不划算。

    Planner 不在此列：它的 `continuity_contract_hint` 走的是「产出本章契约」那条路，
    与这三家「消费上一章契约」语义不同，单独评估。
    """
    if agent_type in _SUPPRESS_HANDOFF_AND_CONTRACT:
        return {"suppress_handoff_and_contract": True}
    return {}




@register(STRATEGY_SHORT_FORM, "execution_brief_boilerplate")
def short_execution_brief_boilerplate() -> dict[str, bool]:
    """短篇简报里哪些长篇兜底块该出现 —— 全部不出现。

    实测一个婚宴题材短篇第 2 节的简报共 1490 字符,其中 1044 字符(70%)是
    `recording_boundary`(纸笔禁令)、`interpretation_boundary`(设备回执三层)、
    `end_state_boundary`、`do_not_turn_into_a_report` 四块硬编码兜底。短篇 planner
    不产出 `end_state`/`state_changes`/`new_stage_delta`,这些块全部走兜底值,于是
    简报里真正属于本节的内容不到三成。
    """
    return {
        "recording_boundary": False,
        "interpretation_boundary": False,
        "end_state_boundary": False,
        "do_not_turn_into_a_report": False,
    }


@register(STRATEGY_SHORT_FORM, "execution_brief_extras")
def short_execution_brief_extras(
    contract: dict[str, Any] | None,
    outline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """短篇简报要补的内容：情绪曲线、节拍、角色目标。

    这些字段短篇 planner 确实会产出，但 ``build_chapter_contract`` 是长篇形状的，
    不会把它们带进契约，长篇简报的 ``chapter_execution`` 投影里也没有位置 —— 于是
    「幕后执行参考」里没有本节的执行要点。正文侧另有一条 ``chapter_outline`` 通路
    带着它们，所以不是内容损失；补进简报是为了让简报名副其实。

    优先读大纲（字段的真实来源），契约兜底。
    """
    merged: dict[str, Any] = {}
    for source in (contract, outline):
        if isinstance(source, dict):
            for key in ("emotional_arc", "beats", "character_goals"):
                value = source.get(key)
                if value not in (None, "", [], {}):
                    merged[key] = value
    merged["short_form_rules"] = [
        "本节要有钩子、实质推进和情绪落点，不要压成单一增量。",
        "反转落地前先确认铺垫已在前文出现。",
        "全篇人称统一；第一人称不得越权。",
        "若为最后一节：把线索收成确定结论，不要悬置。",
    ]
    return merged
