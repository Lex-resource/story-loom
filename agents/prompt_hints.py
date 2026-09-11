"""Helpers for constructing LLM prompt hint blocks.

Centralizes the ``\\n\\n【label】\\n{content}`` pattern duplicated across
planner.py, writer.py, and editor.py. Each helper returns "" when the
input is empty/falsy so callers can unconditionally pass results to
``safe_format`` without extra branching.
"""
import re
import string
from agents.base import sanitize_untrusted_content

def hint_block(header: str, content: str, suffix: str = "") -> str:
    """Build a ``\\n\\n{header}\\n{content}{suffix}`` hint block.

    ``header`` is the full label string including any 【】 markers
    (e.g. ``"【用户实时干预指令 — 必须优先执行】"``). Returns empty string
    when ``content`` is falsy. Content is sanitized via
    ``sanitize_untrusted_content`` to prevent prompt injection. Optional
    ``suffix`` is appended verbatim (used for tail explanatory text such
    as the editor's decision guidance).
    """
    if not content:
        return ""
    body = f"\n\n{header}\n{sanitize_untrusted_content(content)}"
    if suffix:
        body += suffix
    return body


def intervention_hint(intervention: str) -> str:
    """Hint block for user real-time intervention (used by planner/writer/editor)."""
    return hint_block("【用户实时干预指令 — 必须优先执行】", intervention)


def vector_context_hint(vector_context: str) -> str:
    """Hint block for retrieved vector context (used by writer/editor)."""
    return hint_block("【相关背景补充】", vector_context)


def narrative_index_hint(index_context: str, agent_type: str = "writer") -> str:
    """Render accepted narrative projections as bounded continuity guidance."""
    if not index_context:
        return ""
    return hint_block(
        f"【叙事索引·{agent_type} 专属投影】",
        index_context,
        suffix=(
            "\n\n使用边界：这是由已发布章节确定性投影出的事件、段落、阶段和伏笔关联，"
            "只能用于定位已发生内容和承接关系；不能替代角色卡、硬事实或未知边界。"
        ),
    )


_AGENT_MEMORY_GUIDANCE = {
    "planner": (
        "优先使用剧情阶段、当前场景块、角色弧、主线推进和到期伏笔；"
        "只把已接受记忆当作事实，候选线索只规划调查或推进动作。"
    ),
    "writer": (
        "优先使用当前场景块、出场角色的上一章状态、已接受硬事实、章节交接包和章节契约；"
        "不要用候选线索补全身份、因果、地点或生死。"
    ),
    "editor": (
        "优先核对已接受硬事实、角色状态、章节契约、交接包和伏笔动作；"
        "只把有直接证据的冲突判为硬冲突。"
    ),
    "validator": (
        "优先检查已接受硬事实、时间线、角色状态、章节契约和交接包；"
        "candidate/generated 只能作为待核对线索，unknown 不得被正文确认。"
    ),
    "extractor": (
        "优先识别本章形成的场景状态、角色状态、主线推进和伏笔变化；"
        "将未经审定的新内容沉淀为 candidate/generated，不直接升级为事实。"
    ),
}


def novel_memory_hint(memory_context: str, agent_type: str = "writer") -> str:
    """Render role-specific layered memory as bounded advisory context."""
    if not memory_context:
        return ""
    guidance = _AGENT_MEMORY_GUIDANCE.get(agent_type, _AGENT_MEMORY_GUIDANCE["writer"])
    return hint_block(
        f"【分层记忆补充·{agent_type} 专属召回】",
        memory_context,
        suffix=f"\n\n使用边界：{guidance}",
    )


def continuity_handoff_hint(handoff_context: str) -> str:
    return hint_block(
        "【上一章结构化交接包（优先承接，未知字段禁止自行补全）】",
        handoff_context,
    )


def continuity_contract_hint(contract_context: str) -> str:
    return hint_block(
        "【本章连续性契约（Planner、Writer、Editor、Validator 必须使用同一份）】",
        contract_context,
    )


def authority_boundary_hint() -> str:
    return (
        "\n\n【记忆权威边界（V3）】\n"
        "- published/user/frozen/accepted：只有在输入中明确标注来源时，才可直接作为事实使用。\n"
        "- candidate/generated：只能作为待核对线索，不能确认身份、因果、生死、地点归属或物品状态。\n"
        "- unknown：可以描写观察、疑问、调查和悬念，但禁止补全未知结论。\n"
        "- 章节契约中的 required_events 是可执行的动作或场面，不会自动提升 candidate/generated/unknown 的证据等级。\n"
        "若候选线索与角色卡、已发布正文、冻结设定或 accepted 记忆冲突，以权威来源为准；若证据不足，保留不确定性。"
    )


def v7_continuity_state_hint(agent_type: str) -> str:
    """Protect cross-chapter item transitions and evidence attribution."""
    guidance = {
        "planner": "规划物品动作前先核对 item_state_ledger；只能规划账本允许的下一步，不得重复已完成的开封、转移或封存。证据关联不等于人物归属或亲自执行。",
        "writer": "把 item_state_ledger 当作物品状态账本：当前状态和已完成转移不可回滚或重复。关联、相似、指向只能写成线索，不能写成归属、亲自执行或因果确认。",
        "editor": "逐项核对物品状态转移是否与 item_state_ledger 单调一致；把证据关联被写成归属/执行/因果的句子局部改为限定表达，除非造成硬冲突不要退回 Writer。",
        "validator": "将重复开封、重复转移、状态回滚和证据关联升级为归属/执行/因果视为硬连续性问题；报告账本条目、正文证据和冲突来源。",
        "extractor": "只从正文明确发生的物品状态转移提取候选，保留 source_chapter、operation 和 state；证据关联不得提取为人物归属或亲自执行事实。",
    }
    return "\n\n【V7 跨章物品账本与证据边界】\n" + guidance.get(agent_type, guidance["writer"])


def v32_prompt_surface_hint(agent_type: str) -> str:
    """Replace the accumulated continuity rulebook with one role-specific surface."""
    guidance = {
        "planner": (
            "只用已接受/已发布/冻结事实规划本章。先区分上一章已继承的可观察状态与本章真正发生的变化；"
            "required_events 只写角色动作、选择、阻力和可见后果，unknown/candidate 只写观察、追问或调查。"
            "不要把未知关系写成因果、先后、来源、身份或控制结论，也不要把后台字段写成剧情事件。"
        ),
        "writer": (
            "先写自然场景和人物目标，再遵守硬事实。按‘承接已观察状态 -> 角色动作/选择 -> 可见后果’推进；"
            "交接包和契约是幕后边界，不是正文清单。candidate/unknown 只能表现为观察、疑问或调查，"
            "不能补成因果、先后、来源、身份、控制或未来事实。界面读取不等于实体变化，实体变化必须有角色动作或保持未知。"
        ),
        "editor": (
            "先保留自然叙事和人物行动。只有硬事实、核心事件缺失、严重断章或无法局部修复的连续性冲突才要求重写；"
            "因果/时间/来源/身份措辞越界、说明书口吻和轻微节奏问题，直接改最小句子并保留契约与未知边界。"
        ),
        "validator": (
            "只把已确认事实、章节契约、角色动作和正文可见证据当作校验依据。硬设定、角色状态、物品、时间线、"
            "核心事件或动作归属冲突才 block；观察被升级为因果、先后、来源、身份或控制结论也 block。"
            "文风、重复和证据字段缺失若不造成硬冲突，只列 warning，并给出正文证据与冲突来源。"
        ),
        "extractor": (
            "只沉淀本章正文明确发生的动作、状态变化和伏笔推进。上一章未改变的状态标为 inherited_current；"
            "观察、猜测、candidate 和 unknown 保持不确定，不写成未来事实、因果、先后、来源、身份或控制事实。"
        ),
    }
    return "\n\n【V32 精简连续性提示面】\n" + guidance.get(agent_type, guidance["writer"])


def v33_memory_update_protocol_hint(agent_type: str) -> str:
    """Keep extractor patches aligned with the layered-memory update protocol."""
    guidance = {
        "extractor": (
            "【V33 记忆更新协议】按 memory_key 区分更新类型：新键才使用 upsert；已有键的本章观察、人物动态状态、"
            "世界规则的可观察推进、伏笔或主线推进使用 append_progress。只有正文明确推翻既有生成记忆时，才使用 merge/upsert，"
            "并在 data 中加入 \"replacement\": true 与简短依据；resolve/cancel 只用于正文明确回收或作废。"
            "人物静态身份、核心设定和冻结字段不通过动态 patch 覆盖；候选线索保持 candidate/unknown，不升级为硬事实。"
        ),
    }
    hint = guidance.get(agent_type, "")
    return f"\n\n{hint}" if hint else ""


def v34_context_ownership_hint(agent_type: str) -> str:
    """Keep each continuity block responsible for one kind of truth."""
    guidance = {
        "planner": (
            "交接包负责上一章已经成立的继承状态，分层记忆只补充未被交接包覆盖的已接受变化；"
            "章节计划只写本章新增动作、选择和可见后果，不把继承状态重复列为新事件。"
        ),
        "writer": (
            "交接包只用于开场承接，章节契约只用于本章动作，角色卡只用于角色事实，分层记忆只补充未覆盖的已接受变化。"
            "同一事实已有权威来源时不要在另一块上下文中重复解释；candidate/unknown 只能写成观察或疑问。"
        ),
        "editor": (
            "按来源归属判断问题：交接包核对继承状态，章节契约核对本章动作，角色卡核对角色事实，分层记忆只作补充。"
            "同一事实重复出现不算新冲突，优先修复最小越界句。"
        ),
        "validator": (
            "按来源归属校验：交接包是上一章状态，章节契约是本章执行要求，角色卡是角色硬事实，分层记忆只补充已接受变化。"
            "不要因为多个上下文块重复表达同一事实而新增冲突；只阻断与权威来源不一致的正文。"
        ),
        "extractor": (
            "只从本章正文提取新增变化；上一章交接包中的 inherited_current 不重复写成新变化。"
            "已有 memory_key 的新观察按 append_progress 沉淀，并保持原有权威边界。"
        ),
    }
    hint = guidance.get(agent_type, guidance["writer"])
    return f"\n\n【V34 上下文所有权与当前状态投影】\n{hint}"


def v35_writer_narrative_hint(agent_type: str) -> str:
    """Keep the Writer focused on scene execution after context projection."""
    if agent_type != "writer":
        return ""
    return (
        "\n\n【V35 叙事执行模式】\n"
        "叙事执行简报已经把上一章承接、本章动作、结尾目标和未知边界合并；"
        "它是幕后参考，不是需要逐项复述的清单。先让人物在当前场景中做出选择，"
        "再用可见后果推进节拍；连续性规则只约束事实和动作归属，不要把正文写成记录、报告或审计说明。"
    )


def v36_artifact_commitment_hint(agent_type: str) -> str:
    """Make recording actions explicit without inventing physical artifacts."""
    guidance = {
        "planner": (
            "记录、保存或留存信息时先选择无新增实体物品的动作：界面内记录、口述复述、纯观察，"
            "或使用 item_state_ledger 已登记且已在场的设备。账本没有对应条目时，不要规划笔记本、纸张、"
            "记录页、笔、便签、原件、副本、附件或文件夹；把‘记录证据’写成记录方式，而不是新增物品。"
        ),
        "writer": (
            "【V36 记录动作承诺】正文需要‘记录/保存/留存信息’时，默认写成界面内记录、口述复述、纯观察，"
            "或使用 item_state_ledger 已登记且已在场的设备。账本没有对应条目时，禁止为了完成记录动作新增笔记本、"
            "纸张、纸面、记录页、笔、便签、原件、副本、附件或文件夹；不要用具体物品替代抽象记录动作。"
            "只有账本明确登记该物品且本章动作允许，才描写持有、书写、翻页、拍摄或转移。"
        ),
        "editor": (
            "发现正文为记录信息凭空新增笔记本、纸张、记录页、笔、便签、原件、副本、附件或文件夹时，"
            "局部改为界面内记录、口述复述、纯观察或已登记设备；只有与既有账本冲突的物品状态才升级为重写理由。"
        ),
        "validator": (
            "区分抽象记录动作和具体记录物品：界面内记录、口述复述、纯观察不是新增实体；"
            "笔记本、纸张、记录页、笔、便签、原件、副本、附件或文件夹用于记录且没有对应 item_state_ledger 条目时，"
            "报告为硬 item_state 冲突并引用正文物品证据与空/不匹配账本。"
        ),
        "extractor": (
            "记录、保存或留存的信息动作本身不是新物品。只有正文明确出现且 item_state_ledger 有对应条目的实体，"
            "才提取为物品状态；未登记的具体记录物品保留为候选冲突，不得直接进入 accepted 记忆。"
        ),
    }
    return "\n\n【V36 记录动作与实体承诺边界】\n" + guidance.get(agent_type, guidance["writer"])


def v37_observation_interpretation_hint(agent_type: str) -> str:
    """Keep visible observations, character guesses, and investigations separate."""
    guidance = {
        "planner": (
            "把未知内容分成三类：observed 是界面/设备/回执明确显示或角色直接感知的内容，"
            "tentative 是角色保留‘也许/可能/尚不能判断’的暂时解释，investigation 是追问、核对或查询动作。"
            "required_events 只能规划角色动作和可见后果；不得把设备提示规划成设备意图、已经发生的历史事件、"
            "必然存在的目标，或把残缺片段规划成完整记录。"
        ),
        "writer": (
            "【V37 观察解释三层边界】把屏幕、设备或回执写出的原文当作 observed；人物可以提出 tentative 猜测，"
            "但必须保留‘也许/可能/无法判断’，再用 investigation 动作推进。残缺片段、显示时间、相邻出现或重复响应，"
            "不能升级成已经发生的历史事件、完整记录、真实地点、来源、身份或因果。设备的提示、拒答和响应也不等于"
            "设备的意图、要求、控制动作或某个目标已经存在。比如“历史回执：片段”只能写成界面显示的片段，"
            "“下一份回执已待取回”只能作为新提示，不能写成设备要求角色寻找某条已发生记录。"
        ),
        "editor": (
            "按 observed / tentative / investigation 三层检查解释越界。把‘界面显示残缺片段’与‘这一定是已发生历史记录’、"
            "把‘设备提示下一份回执’与‘设备要求寻找某条记录’拆开；保留人物猜测和调查目标，但将确定性历史、意图或因果"
            "改成来源限定的观察、疑问或待核对线索。若只是解释措辞越界，局部修复，不退回 Writer。"
        ),
        "validator": (
            "阻断 observed 被升级为 confirmed：残缺/显示/相邻/重复内容不得变成已发生历史、完整记录、真实地点或因果；"
            "设备响应不得单独证明设备意图、要求、控制或目标存在；人物猜测不得被正文收束成事实。报告 observed 原文、"
            "越界解释和 unknown/contract 来源，区分可局部修复的措辞问题与真正事件冲突。"
        ),
        "extractor": (
            "将正文分开提取：observed 只记录可见原文或直接感知，tentative 只能作为 candidate/unknown，"
            "investigation 记录角色下一步动作。不得把残缺回执、显示时间、设备响应或人物解释沉淀为已发生历史、设备意图、"
            "身份、来源或因果事实。"
        ),
    }
    return "\n\n【V37 观察与解释边界】\n" + guidance.get(agent_type, guidance["writer"])


def v38_scene_motion_hint(agent_type: str) -> str:
    """Keep continuity scenes moving instead of repeating checks and summaries."""
    guidance = {
        "planner": (
            "把每个节拍规划成‘角色动作/选择 -> 阻力或新信息 -> 可观察后果’；"
            "同一查询、读取或确认只有在出现新差异、代价或关系变化时才重复。"
            "不要把同一观察改写成多个剧情事件，结尾必须留下角色位置、决定或调查方向的变化。"
        ),
        "writer": (
            "【V38 场景运动与重复信息压缩】每个场景都要发生可见推进：角色做出动作或选择，"
            "遭遇阻力或得到新信息，然后让现场、关系、风险或下一步发生变化。对同一界面文字的重复读取、"
            "确认和复述，只有在出现新的文字差异、实际代价或人物选择时才保留；没有新变化就删掉。"
            "不要连续用‘确认、意识到、说明、无法判断’收束同一未知结论，改用动作、停顿、感官或决定表现。"
            "结尾应落在新的位置、选择或调查问题上，而不是总结本章规则。"
        ),
        "editor": (
            "优先合并没有新信息的重复观察、查询和确认：保留第一次可见证据，只保留后续真正新增的差异、"
            "代价或选择；把审计式总结改成最短的动作、反应或后果。不得为了压缩重复而删除章节契约要求的动作，"
            "也不得补写没有来源的新事实。"
        ),
        "validator": (
            "检查连续核对是否产生新信息、代价或选择；纯重复、说明书口吻和人物反应不足属于质量 warning，"
            "除非同时缺少核心事件或违反硬连续性，不得单独触发重写。阻断时必须引用缺失的契约事件或具体冲突，"
            "不能把‘不够精彩’泛化为重写理由。"
        ),
        "extractor": (
            "只沉淀本章新增的动作、选择、状态差异、关系后果和伏笔推进；同一观察的复述、确认或改写不生成重复记忆。"
            "若没有新差异，保留已有状态和 source_chapter，不创建新的 memory_key。"
        ),
    }
    return "\n\n【V38 场景推进与重复信息压缩】\n" + guidance.get(agent_type, guidance["writer"])


def v39_single_evidence_delta_hint(agent_type: str) -> str:
    """Make each scene carry one evidence pass and one distinct state delta."""
    guidance = {
        "planner": (
            "【V39 单次证据读取与状态增量】先检查上一章已有的观察，再为本章每个节拍指定唯一的 state_delta："
            "新信息、实际代价、人物选择或关系/风险变化四者至少有一项。"
            "同一场景中只能安排一次完整证据读取；后续只能写新的差异、代价或选择，不能把再次查询、再次确认和再次复述拆成独立节拍。"
            "如果一个节拍没有独立 state_delta，就把它合并到相邻节拍，不要用解释填充节拍数量。"
        ),
        "writer": (
            "【V39 单次证据读取与状态增量】同一证据在正文中只完整呈现一次：首次呈现原文，后续只写新增差异或真实代价。"
            "每个场景只保留一次完整的查询/读取/核对过程；重复操作必须带来新结果或明确选择，否则删掉。"
            "一段解释不能代替人物行动：在解释同一未知之后，立即让人物改变位置、策略、风险或调查目标。"
            "每个场景结束时必须留下一个与开场不同的现场状态、人物决定或风险，不要用‘他确认/他意识到/无法判断’连续收束。"
        ),
        "editor": (
            "【V39 单次证据读取与状态增量】逐场检查是否把同一证据完整重复了多次。保留第一次完整读取，"
            "后续只保留真正新增的差异、代价或选择；将没有独立 state_delta 的解释段合并到动作后。"
            "不得为了压缩删除唯一证据或章节核心动作，也不得添加正文没有来源的状态变化。"
        ),
        "validator": (
            "【V39 单次证据读取与状态增量】把同一证据的重复读取、确认或复述标为 warning，除非它导致核心事件缺失或硬连续性冲突。"
            "检查每个场景是否至少产生一个可见 state_delta；只有全章没有剧情推进、缺少契约核心事件或出现硬冲突时才 block。"
            "报告时引用重复证据和缺失的具体动作/后果，不要用‘不够精彩’泛化阻断。"
        ),
        "extractor": (
            "【V39 单次证据读取与状态增量】只为正文中新出现的 state_delta 建立候选变化：新事实、动作后果、人物选择、关系/风险变化。"
            "同一证据的重复读取、确认和复述不生成 patch；已有 memory_key 只在出现真实进展时 append_progress，并保留 source_chapter。"
        ),
    }
    return "\n\n【V39 单次证据读取与状态增量】\n" + guidance.get(agent_type, guidance["writer"])


def v40_contract_state_hint(agent_type: str) -> str:
    """Keep the chapter's terminal state aligned across all agents."""
    guidance = {
        "planner": (
            "【V40 终态边界】end_state 必须表示本章最后已经成立的可观察状态，而不是‘准备/决定/将要’等未完成动作。"
            "beats、required_events 和 state_changes 必须在这个终态处停止；如果结尾停在门槛、决定或等待，就不要同时写已经进入、已经完成或已经改变。"
        ),
        "writer": (
            "【V40 终态边界】章节契约中的 end_state 是本章最终落点。先按正文完成的动作推进，再在 end_state 处收束；"
            "如果前面的节拍写‘准备/决定/将要’，而 end_state 停在动作发生前，不能为了完成节拍越过终态。"
            "只有正文确实改变了已接受事实、时间线、物品/地点状态或核心事件，才需要修正，不要把终态的轻微措辞差异扩写成新事件。"
        ),
        "editor": (
            "【V40 终态边界】把章节结尾统一到契约 end_state 的最后可观察状态。若正文只比终态多出一个‘已经/准备/决定’措辞，"
            "优先局部改写或删去越过终态的短句；不得新增动作，也不得把轻微契约措辞差异升级为 Writer 重写。"
        ),
        "validator": (
            "【V40 终态边界】end_state 是本章终态锚点。区分真正的状态越界与契约文字的轻微歧义："
            "只有正文造成已接受事实、时间线、物品/地点状态或核心事件的真实冲突才 severity=block；"
            "‘决定点/已经进入’这类不影响已接受事实的局部表述不构成硬冲突，应列 warning 或交给 Editor 局部修复。"
        ),
        "extractor": (
            "【V40 终态边界】记忆沉淀以已发布正文中实际发生的最后状态为准；章节契约只帮助确定终态边界。"
            "不要把‘准备/决定/将要’当作已完成动作，也不要为契约措辞差异生成新的 memory_key；真实状态变化才 append_progress。"
        ),
    }
    return "\n\n【V40 终态边界】\n" + guidance.get(agent_type, guidance["writer"])


def v41_narrative_escalation_hint(agent_type: str) -> str:
    """Make repeated investigation chapters change objective or risk."""
    guidance = {
        "planner": (
            "【V41 叙事升级与策略改变】先比较上一章的调查目标、已完成动作和本章 start_state，"
            "再为本章安排一次可观察的策略改变、角色选择、资源/时间代价或风险变化。"
            "同一界面、同一核对路径或同一门禁动作最多安排一次完整读取；换一个字段名称不算新的剧情节拍。"
            "如果未知事实仍不能揭示，就用已知证据推动调查目标、位置、行动限制或选择变化，不得为了制造升级新增未登记实体、身份、因果或权限。"
        ),
        "writer": (
            "【V41 叙事升级与策略改变】完成一次完整证据读取后，必须让角色作出可观察的选择，或让策略、风险、资源/时间成本发生变化。"
            "再次查询、再次保存、再次触碰同一门禁，只有带来明确新结果或真实代价时才保留，不能把换字段、换说法当作升级。"
            "未知信息不能揭示时，使用角色的停留、转移、退出、等待或调查目标改变等已被契约允许的具体行动收束；"
            "不得添加未登记角色、物品、权限、来源或因果来制造冲突。"
        ),
        "editor": (
            "【V41 叙事升级与策略改变】逐场检查正文是否在证据读取后出现可观察的选择、策略变化、代价或风险变化。"
            "合并没有新结果的重复查询、保存、门禁试探和解释，把篇幅留给已有契约支持的行动后果；"
            "只能局部压缩和重排，不得补造新的角色、物品、权限、来源或因果。"
        ),
        "validator": (
            "【V41 叙事升级与策略改变】检查每个主要场景是否在一次证据动作后产生新选择、策略变化、代价或风险变化。"
            "纯重复和人物反应不足属于 writing_quality/plot_progression warning，不能单独触发 Writer 重写；"
            "只有核心事件缺失、严重断章或事实/时间线/物品/地点等硬冲突才阻断。"
        ),
        "extractor": (
            "【V41 叙事升级与策略改变】优先沉淀正文中新出现的角色选择、调查策略变化、资源/时间代价、风险或位置变化，"
            "并保留 source_chapter 和 authority。重复查询、保存、门禁试探或解释不生成新的 memory_key；"
            "没有可观察变化时保留已有状态，不得凭空推断后续目标或因果。"
        ),
    }
    return "\n\n【V41 叙事升级与策略改变】\n" + guidance.get(agent_type, guidance["writer"])


def v42_authority_locked_progression_hint(agent_type: str) -> str:
    """Keep narrative escalation observable and authority-locked."""
    guidance = {
        "planner": (
            "【V42 权威锁定的可观察推进】本章的升级轴只能是正文可观察的行动、位置、允许的调查目标、资源/时间代价或风险变化。"
            "身份、发送者、来源、执行者、归属、因果和历史方向不是可自行创造的 state_delta；没有 accepted/published/frozen 证据时，"
            "只能规划观察、保留多个解释或调查动作。涉及上一章的方向、归属或设备通道时，先按交接包核对，不能用新一章的猜测反转既有状态。"
        ),
        "writer": (
            "【V42 权威锁定的可观察推进】只用已发生的动作、位置、调查目标、资源/时间代价或风险变化推进本章。"
            "模糊的署名、相似身份、相邻时间、脚印方向、设备响应和回执字段只能保持为观察或待核对线索，不能写成身份、发送者、来源、执行者、归属或因果结论。"
            "上一章已经确定的方向、通道、物品状态和行动结果必须保持一致；没有写出中间转变，就不要反向改写。未知事实仍需推进时，让角色改变行动或目标，不要替未知信息补一个解释。"
        ),
        "editor": (
            "【V42 权威锁定的可观察推进】局部修订时保留行动/位置/目标/代价/风险推进，删除或改写把模糊字段升级为身份、来源、执行者、归属、因果的句子。"
            "逐项核对上一章已经发布的方向、通道、物品和行动状态；没有观察到的中间转变时，禁止把本章写成相反状态。不得为了让剧情升级而补造新事实。"
        ),
        "validator": (
            "【V42 权威锁定的可观察推进】身份、发送者、来源、执行者、归属、因果、历史方向、通道状态和物品方向的无证据升级或跨章反转，必须按正文证据与权威来源报告硬冲突。"
            "只有缺少行动/目标/代价/风险推进、重复操作或人物反应不足属于 quality warning，不能单独触发 Writer 重写。"
        ),
        "extractor": (
            "【V42 权威锁定的可观察推进】只沉淀正文直接发生的行动、位置、调查目标、资源/时间代价和风险变化。"
            "署名、相似身份、相邻时间、脚印方向、设备响应和回执字段若没有直接确认，只记录为 candidate/unknown 观察；"
            "不得提取身份、来源、执行者、归属、因果或方向反转，也不得为未知解释创建 accepted memory_key。"
        ),
    }
    return "\n\n【V42 权威锁定的可观察推进】\n" + guidance.get(agent_type, guidance["writer"])


def v43_bounded_hypothesis_progression_hint(agent_type: str) -> str:
    """Allow explicitly bounded hypotheses to move a scene without making facts."""
    guidance = {
        "planner": (
            "【V43 受限假设推进与最小叙事增量】本章只设置一个主叙事增量：角色的可观察选择、行动、位置、调查目标、资源/时间代价或风险变化，"
            "并写出该增量造成的可见后果。未知事实可以产生一个明确标注为‘假设/待核实/工作解释’的调查方向，"
            "但不得把它写成 required_events 中的确认事实，也不得让不可逆行动依赖这个假设。"
            "除主叙事增量外，最多保留一个核心未决问题；不得用换字段、换入口或重复读取代替新进展。"
        ),
        "writer": (
            "【V43 受限假设推进与最小叙事增量】正文必须围绕一个可观察的主叙事增量展开，并在结尾留下明确的行动后果或新约束。"
            "模糊署名、相似身份、相邻时间、脚印方向、设备回执和来源字段可以作为‘假设/待核实/工作解释’推动调查，"
            "但必须保留限定语，不能写成身份、发送者、来源、执行者、归属或因果事实；不可逆行动不能建立在未确认假设上。"
            "证据读取完成后应发生一次选择或策略改变，删除没有新结果的重复查询、保存和试探。"
        ),
        "editor": (
            "【V43 受限假设推进与最小叙事增量】保留一个清晰的行动/选择/位置/目标/代价/风险增量，压缩没有新结果的重复操作。"
            "若正文把候选线索写成确认事实，优先局部补回‘假设/待核实/工作解释’限定；若只涉及限定语而不违反已接受事实，直接修订，不退回 Writer。"
            "不得为了补足推进新增角色、物品、权限、来源、因果或不可逆结果。"
        ),
        "validator": (
            "【V43 受限假设推进与最小叙事增量】检查正文是否有一个可观察的主叙事增量，以及候选线索是否明确标为假设/待核实/工作解释。"
            "明确限定的假设不是事实确认，也不应单独形成重写理由；只有它被写成已确认事实、违反已接受事实，或导致不可逆结果时，才报告硬冲突。"
            "重复操作、缺少选择或叙事增量不足属于 quality warning，不能单独触发 Writer 重试。"
        ),
        "extractor": (
            "【V43 受限假设推进与最小叙事增量】只沉淀正文直接发生的主叙事增量及其可见后果。"
            "明确标为假设/待核实/工作解释的内容只能记录为 candidate/unknown 线索并保留限定语，不能生成 accepted 身份、来源、执行者、归属、因果或方向事实。"
            "重复查询、保存、门禁试探和说明不生成新的 memory_key。"
        ),
    }
    return "\n\n【V43 受限假设推进与最小叙事增量】\n" + guidance.get(agent_type, guidance["writer"])


# ---------------------------------------------------------------------------
# 冻结的 A28/V43 生产表面
# ---------------------------------------------------------------------------
# 以下每个 agent 的 hint 栈就是 PRODUCTION.md 验证过的 A28/V43 配置
# （七维平均 8.601、9/9 章零内容重试）。函数名保留 vNN_ 前缀，使每条规则仍能
# 追溯到 docs/research/ 里的版本记录。
#
# 各 agent 的栈**不相同**，这是实测确认的，不要"统一"它们：
#   * writer    以 v35_writer_narrative_hint 收尾（不是 v34+v32）
#   * extractor 比其他 agent 多一个 v33_memory_update_protocol_hint
#   * validator 另在 sys_prompt 末尾无条件追加 v7_continuity_state_hint
#
# 研究版本（V44–V66）通过 services/version_surface.research_override 整体替换
# 这里的返回值，而不是在栈里叠加。

_V43_COMMON_TAIL = (
    v41_narrative_escalation_hint,
    v40_contract_state_hint,
    v39_single_evidence_delta_hint,
    v38_scene_motion_hint,
    v37_observation_interpretation_hint,
    v36_artifact_commitment_hint,
)

_V43_AGENT_STACKS: dict[str, tuple] = {
    "planner": (
        v43_bounded_hypothesis_progression_hint,
        v42_authority_locked_progression_hint,
        *_V43_COMMON_TAIL,
        v34_context_ownership_hint,
        v32_prompt_surface_hint,
    ),
    "writer": (
        v43_bounded_hypothesis_progression_hint,
        v42_authority_locked_progression_hint,
        *_V43_COMMON_TAIL,
        v35_writer_narrative_hint,
    ),
    "editor": (
        v43_bounded_hypothesis_progression_hint,
        v42_authority_locked_progression_hint,
        *_V43_COMMON_TAIL,
        v34_context_ownership_hint,
        v32_prompt_surface_hint,
    ),
    "validator": (
        v43_bounded_hypothesis_progression_hint,
        v42_authority_locked_progression_hint,
        *_V43_COMMON_TAIL,
        v34_context_ownership_hint,
        v32_prompt_surface_hint,
    ),
    "extractor": (
        v43_bounded_hypothesis_progression_hint,
        v42_authority_locked_progression_hint,
        *_V43_COMMON_TAIL,
        v34_context_ownership_hint,
        v33_memory_update_protocol_hint,
        v32_prompt_surface_hint,
    ),
}


def generation_hints(agent_type: str, novel_format: str | None = None) -> str:
    """该 agent 的完整生成 hint 表面。

    三层解析，对应两条正交的接缝：

    1. **版本轴**（``services/version_surface``）—— 研究运行整体替换本栈
    2. **格式轴**（``services/workflow_surface``）—— 短篇等非长篇工作流有自己的栈
    3. 都让路时返回冻结的 A28/V43 长篇栈

    ``novel_format=None`` 表示没有工作流上下文，按长篇冻结点处理。因此所有只传
    ``agent_type`` 的既有调用点行为不变，V43 黄金快照不动。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("generation_hints", agent_type)
    if override is not NO_OVERRIDE:
        return override

    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    workflow = workflow_override("generation_hints", novel_format, agent_type)
    if workflow is not NO_WORKFLOW_OVERRIDE:
        return workflow

    stack = _V43_AGENT_STACKS.get(agent_type, _V43_AGENT_STACKS["writer"])
    return "".join(hint(agent_type) for hint in stack)


def chapter_contract_output_requirements(novel_format: str | None = None) -> str:
    """Planner 的章节契约输出要求（长篇冻结在 A28/V43）。

    短篇由格式轴接管：长篇要求的八个字段在短篇 planner 的 schema 里一个都没有，而
    模板同时命令“严格匹配以下结构”—— 这条矛盾指令是短篇契约字段大面积为空、进而让
    执行简报落回长篇兜底的源头。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("chapter_contract_output_requirements")
    if override is not NO_OVERRIDE:
        return override

    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    workflow = workflow_override("chapter_contract_output_requirements", novel_format)
    if workflow is not NO_WORKFLOW_OVERRIDE:
        return workflow

    return (
        "\n\n【V34 章节契约输出要求】\n"
        "输出 required_events、uncertain_events、continuity_from_previous、state_changes、"
        "foreshadowing_actions、forbidden_deviations、unknown_boundary 和 continuity_contract。"
        "continuity_from_previous 只记录上一章继承状态；required_events 和 state_changes 只记录本章新增动作与可见后果。"
        "不得把继承状态重复包装成新的剧情事件。"
    )


def writer_context_policy() -> dict[str, bool]:
    """Writer 收到哪些上下文块（冻结在 A28/V43）。

    V35 起交接包与章节契约归 execution brief 所有，Writer 不再收原始副本，
    上一章结尾也不再单独重复。生产因此两项都抑制；研究运行可整体覆盖。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("writer_context_policy")
    if override is not NO_OVERRIDE:
        return override

    return {
        "suppress_handoff_and_contract": True,
        "suppress_previous_ending": True,
    }


# Editor / Validator / Extractor 默认全收（长篇冻结点的行为，字节不变）。
_AGENT_CONTEXT_KEPT: dict[str, bool] = {"suppress_handoff_and_contract": False}


def agent_context_policy(agent_type: str, novel_format: str | None = None) -> dict[str, bool]:
    """Editor / Validator / Extractor 是否收到交接包与章节契约的原始副本。

    Writer 由 `writer_context_policy()` 单独管 —— 那是 V35 起的**研究轴**决策（两份 payload
    归 execution brief 所有），与工作流无关。这三家没有 execution brief，长篇下必须继续收到
    原始副本，所以默认不抑制。

    短篇由格式轴接管：交接包的 `item_states` / `evidence_states` / `completed_event_ledger`
    和契约的 `state_changes` / `new_stage_delta` / `end_state_boundary` 都是跨章物品与证据账本
    机制，短篇 planner 一个都不产出 —— 投影出来是空壳套长篇语汇。

    抑制交接包还有一个附带效果：`previous_ending_for_prompt` 在交接包为空时会回落到完整的
    上一章结尾（见该函数），于是短篇 Editor/Validator 拿到的是直白的「上一节结尾」而不是
    结构化交接包，这正是短篇需要的形状。
    """
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    override = workflow_override("agent_context_policy", novel_format, agent_type)
    if override is not NO_WORKFLOW_OVERRIDE:
        return {**_AGENT_CONTEXT_KEPT, **override}
    return _AGENT_CONTEXT_KEPT


def writer_rewrite_requirements() -> str:
    """Writer 的定点重写要求（冻结在 A28/V43）。"""
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("writer_rewrite_requirements")
    if override is not NO_OVERRIDE:
        return override

    return (
        "\n\n【V5 定点重写要求】\n"
        "若收到上一轮校验或编辑错误，逐条处理其中的正文证据、冲突事实和修复建议；"
        "只修改被证据定位的问题，保留章节契约、上一章交接和已确认事实。"
        "禁止使用“重新写得更好”这类泛化目标，也不得借重写补全 unknown 或 candidate/generated 线索。"
    )


def repair_surface_hints(agent_type: str) -> str:
    """Editor 强制修订 / 去风格化，以及 Extractor 辅助抽取路径上的额外 hint。

    A28/V43 下这些路径不附加额外 hint（对应的链整段起于 V50）。研究运行
    V50+ 会由覆盖层给出内容。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("repair_surface_hints", agent_type)
    if override is not NO_OVERRIDE:
        return override

    return ""


def editor_policy(novel_format: str | None = None) -> dict[str, object]:
    """Editor 的审阅策略与结构开关（长篇冻结在 A28/V43）。

    * ``review_strategy`` —— V5 起的低重试审阅策略文本
    * ``project_outline`` —— V44 起才把单章大纲投影为执行视图；V43 用原始大纲
    * ``long_form_quality_contract`` —— V19 起长篇附加七维质量契约
    * ``research_response_schema`` —— V1 起长篇要求七维评分 schema

    短篇由格式轴接管。注意本函数的返回值以前是**无条件**追加到 Editor system prompt 的
    （``agents/writing/editor.py``），末句要求 evaluations 追加 ``chapter_continuity`` 与
    ``foreshadowing_payoff``，而短篇的响应 schema 只有五维 —— 短篇 Editor 因此长期收到
    自相矛盾的指令，多产的两维也没有消费者。短篇换成自己的逐节两维。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("editor_policy")
    if override is not NO_OVERRIDE:
        return override

    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    workflow = workflow_override("editor_policy", novel_format)
    if workflow is not NO_WORKFLOW_OVERRIDE:
        return workflow

    return {
        "review_strategy": (
            "\n\n【低重试审阅策略】\n"
            "只有硬性设定/时间线冲突、核心事件缺失、严重断章或无法局部修复的结构问题才允许 decision= rewrite。"
            "文风、轻微节奏和局部措辞问题必须直接在 edited_content 中修复。"
            "除原有五维评分外，evaluations 增加 chapter_continuity 和 foreshadowing_payoff 两项，均为 1-10 分并引用具体依据。"
        ),
        "project_outline": False,
        "long_form_quality_contract": True,
        "research_response_schema": True,
    }


_VALIDATOR_EXTRA_REQUIREMENTS_V43 = "\n【校验器额外要求】角色事实、首次发生章节、地点、能力、关系和伤势属于硬规则。发现正文与截至本章已确认事实冲突时，必须输出 severity=block，并在 evidence 与 conflicts_with 中分别引用正文证据和冲突事实。不要把这类问题降级为 warning。注意：本章单章大纲中的 required_changes、end_state、beats 是当前章节允许落地的新事实来源；如果正文按大纲给出了合理触发和过渡，不得仅因为上一章角色卡尚未记录该事实就判定冲突。只有新事实违反既有硬事实、物品消耗状态、死亡状态或与本章大纲相互矛盾时才阻断。"


def validator_extra_requirements(novel_format: str | None = None) -> str:
    """Validator 在 hint 栈之后追加的额外硬规则（长篇冻结在 A28/V43）。

    长篇版本引用 ``required_changes`` 与 ``end_state`` —— 短篇 planner 的 schema 里没有
    这两个字段，只有 ``key_events``/``beats``/``emotional_arc``。短篇由格式轴换成引用
    自己真实存在的字段。
    """
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    workflow = workflow_override("validator_extra_requirements", novel_format)
    if workflow is not NO_WORKFLOW_OVERRIDE:
        return workflow

    return _VALIDATOR_EXTRA_REQUIREMENTS_V43


def validator_trailing_hint(novel_format: str | None = None) -> str:
    """Validator system prompt 末尾追加的跨章物品账本提示（长篇冻结在 A28/V43）。

    短篇没有 ``item_state_ledger``，这段提示对它是纯噪声，格式轴返回空串。
    """
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    workflow = workflow_override("validator_trailing_hint", novel_format)
    if workflow is not NO_WORKFLOW_OVERRIDE:
        return workflow

    return v7_continuity_state_hint("validator")


def previous_ending_for_prompt(previous_ending: str, handoff_context: str) -> str:
    """Avoid pasting the same ending beside handoff.exact_ending in V10."""
    if handoff_context:
        marker = "【注意：后续章节"
        if marker in (previous_ending or ""):
            return previous_ending[previous_ending.index(marker):]
        return ""
    return previous_ending or ""


def reference_style_hint(reference_style: str, label: str = "写作风格参考") -> str:
    """Hint block for reference style.

    ``label`` differs between planner (``"策划风格参考"``) and writer/editor
    (``"写作风格参考"``).
    """
    return hint_block(f"【{label}】", reference_style)


def validation_errors_hint(errors: str, suffix: str = "") -> str:
    """Hint block for validation errors with optional suffix explanation."""
    return hint_block("【关键】内容规则与安全校验错误提示：", errors, suffix=suffix)


def append_missing_hints(prompt_str: str, template: str, **hints) -> str:
    """Append hint values whose placeholder is missing from the template.

    Avoids duplicating the ``string.Formatter().parse()`` fallback logic
    previously inlined twice in planner.py. Only non-empty hint values are
    appended.
    """
    parsed_keys = {tup[1] for tup in string.Formatter().parse(template) if tup[1] is not None}
    for name, value in hints.items():
        if value and name not in parsed_keys:
            prompt_str += value
    return prompt_str


def compact_layered_prompt(prompt: str) -> str:
    """Remove empty legacy state labels once layered prompts are enabled."""
    legacy_labels = (
        "当前世界观状态：",
        "当前世界观状态",
        "世界观状态：",
        "当前世界状态：",
        "当前人物状态：",
        "人物状态：",
        "当前伏笔账本：",
        "伏笔账本：",
        "当前主线进度：",
        "主线进度：",
        "当前剧情进度：",
        "当前剧情线索：",
    )
    empty_block_headers = {
        "世界状态",
        "当前世界状态",
        "人物状态",
        "当前人物状态",
        "伏笔",
        "当前伏笔账本",
        "剧情线",
        "当前主线进度",
        "当前剧情进度",
        "当前剧情线索",
        "历史问题总结",
    }
    lines = prompt.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        header_name = stripped.strip("【】： ")
        if header_name in empty_block_headers:
            probe = index + 1
            while probe < len(lines) and not lines[probe].strip():
                probe += 1
            if probe < len(lines) and lines[probe].strip() == "<user_content>":
                close = probe + 1
                while close < len(lines) and not lines[close].strip():
                    close += 1
                if close < len(lines) and lines[close].strip() == "</user_content>":
                    index = close + 1
                    while index < len(lines) and not lines[index].strip():
                        index += 1
                    continue
        if any(stripped == label for label in legacy_labels):
            next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if not next_line or next_line.startswith(("【", "当前", "历史", "上一", "本章", "====")):
                index += 1
                while index < len(lines) and not lines[index].strip():
                    index += 1
                continue
        kept.append(line)
        index += 1
    return "\n".join(kept).replace("\n\n\n", "\n\n").strip()
