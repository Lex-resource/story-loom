"""V44–V66 与其它非生产版本的 prompt hint。

这些函数在 A28/V43 生产冻结点下**不可达**（实测追踪确认），因此从
`agents/prompt_hints.py` 移到研究覆盖层。函数体逐字节保持原样，
以便 V44–V66 的历史实验仍可复现。

生产可达的 13 个版本化 hint（v7、v32–v43）留在 `agents/prompt_hints.py`。
"""
from __future__ import annotations

import re

from agents.base import sanitize_untrusted_content  # noqa: F401  部分 hint 通过 hint_block 间接使用
from agents.prompt_hints import (
    hint_block,  # noqa: F401
    # 留在生产的 13 个可达 hint。研究的 pre-V44 链需要复用它们组装历史版本；
    # 依赖方向是 research -> production，符合分层。这些函数已无版本门，
    # 只在链选中它们时被调用。
    v7_continuity_state_hint,
    v32_prompt_surface_hint,
    v33_memory_update_protocol_hint,
    v34_context_ownership_hint,
    v35_writer_narrative_hint,
    v36_artifact_commitment_hint,
    v37_observation_interpretation_hint,
    v38_scene_motion_hint,
    v39_single_evidence_delta_hint,
    v40_contract_state_hint,
    v41_narrative_escalation_hint,
    v42_authority_locked_progression_hint,
    v43_bounded_hypothesis_progression_hint,
)
from services.version_surface import NO_OVERRIDE

from research.prompt_versions.registry import register
from research.prompt_versions.version_order import (
    ariadne_series_at_least,
    prompt_version_at_least,
)


def v6_continuity_quality_hint(agent_type: str) -> str:
    """Add V6 evidence-language and technical-density guidance by agent role."""
    if not prompt_version_at_least("V6"):
        return ""
    guidance = {
        "writer": (
            "【V6 证据语言闸门】\n"
            "- published/user/frozen/accepted 才能使用无保留的确认句；candidate/generated/unknown 必须用观察、归因、疑问或调查动作表达。\n"
            "- 未确认的身份、来源、因果、地点、生死和能力，不得在段末用“就是/确认是/证明了/来自/因此可知”等句式收束；改为“只能说明/尚不能判断/留下待核对线索”。\n"
            "- 每段最多集中呈现一组技术字段；连续两段出现设备或字段说明时，下一段必须通过人物动作、感官反应、对话或选择推进，不要重复解释同一字段。\n"
            "- 技术字段必须服务于可见行动和因果，不要用新增术语替代人物选择。"
        ),
        "validator": (
            "【V6 证据语言与信息密度校验】\n"
            "重点检查 candidate/generated/unknown 是否被无限定确认句升级为身份、来源、因果、地点、生死或能力事实；若发现，引用包含确认语句的完整正文证据。\n"
            "同时检查连续技术字段是否造成因果跳跃或重复解释；仅属局部表达问题时列为 warning，不得因此触发内容重试。"
        ),
        "editor": (
            "【V6 局部修订边界】\n"
            "优先把低置信度线索的确认句改成有来源限定的观察或调查表达，并压缩重复技术字段；除非改变会造成硬事实、时间线或章节契约冲突，否则直接局部修订，不退回 Writer。"
        ),
    }
    return "\n\n" + guidance.get(agent_type, guidance["writer"])


def v8_evidence_state_hint(agent_type: str) -> str:
    """Add V8's unified evidence-object and compact-context rules."""
    if not prompt_version_at_least("V8"):
        return ""
    guidance = {
        "planner": "先读取 evidence_state_ledger，区分物品、能力和署名命题；只规划可观察的核对、使用或调查动作，不规划未经证实的归属、执行者或能力升级。",
        "writer": "evidence_state_ledger 是证据命题账本，不是剧情结论。只能复述 proposition 或描写核对/观察；能力响应不等于永久能力，署名不等于本人留下，时间相邻不等于因果。",
        "editor": "优先局部修复 evidence_state_ledger 中的状态升级：把身份、归属、执行、能力和因果断言改为来源限定的观察；只有改变章节契约或硬事实时才退回 Writer。",
        "validator": "逐项核对物品、能力、署名三类证据对象；若正文把命题升级成身份、归属、亲自执行、永久能力或因果事实，必须引用 proposition、正文证据和来源章节并阻断。",
        "extractor": "从正文提取物品、能力和署名命题时保留证据等级与 source_ref；没有直接证据只能生成 candidate，不得把作者、执行者、能力来源写成 accepted。",
    }
    return "\n\n【V8 统一证据对象与紧凑交接】\n" + guidance.get(agent_type, guidance["writer"])


def v9_temporal_evidence_hint(agent_type: str) -> str:
    """Prevent uncalibrated clock values from becoming event ordering."""
    if not prompt_version_at_least("V9"):
        return ""
    guidance = {
        "planner": "跨系统时间只能规划为并列显示值、数值差异或待校准关系；不得规划‘广播前/后’、先发生/后发生或由时间差推出因果，除非同一已校准时钟直接证明。",
        "writer": "不同终端或时间源未校准时，只写‘界面显示值分别为’、‘数值差异待比对’；禁止把它们写成实际发生在广播之前/之后、早于/晚于、先后顺序或因果证据。疑问句也不能预设主动推送者或操作者。",
        "editor": "把未经同一校准时钟证明的‘前后/之前/之后/先后’改成并列显示值和待核对关系；删除疑问句中预设来源、推送者或操作者的措辞。",
        "validator": "跨系统时钟未校准时，‘前后、之前、之后、先后、早于、晚于、随后因此’均不得作为实际时间关系；发现无限定使用必须引用正文和时间源冲突并阻断。",
        "extractor": "提取时间证据时保留显示终端、原始字段和校准状态；只记录数值差异，不提取事件先后或时间因果为 accepted 命题。",
    }
    return "\n\n【V9 跨系统时间证据闸门】\n" + guidance.get(agent_type, guidance["writer"])


def v10_context_compaction_hint(agent_type: str) -> str:
    """Explain the single-owner rule for compact V10 context blocks."""
    if not prompt_version_at_least("V10"):
        return ""
    guidance = {
        "planner": "结构化交接包是上一章结尾和证据边界的唯一来源；分层记忆只补充剧情阶段、角色弧和到期伏笔。不要要求缺失的旧字段自动补全。",
        "writer": "结构化交接包是上一章结尾和证据边界的唯一来源；章节契约只规定本章动作，不重复解释交接账本。角色卡只提供静态设定和截至上一章的状态。",
        "editor": "结构化交接包、章节契约和角色卡各有唯一职责；相同事实出现多次时按交接包/角色卡/契约的权威边界核对，不把重复文本当成新增证据。",
        "validator": "只按结构化交接包、章节契约、角色卡和 accepted 记忆的职责核验；被裁剪的来源仍可在审计快照中追溯，不得因缺少重复描述而推断未知事实。",
        "extractor": "交接包用于识别上一章既有状态，章节契约用于区分本章计划；只从正文提取新增事实，不因上下文中的重复描述生成重复记忆。",
    }
    return "\n\n【V10 上下文单一来源与预算】\n" + guidance.get(agent_type, guidance["writer"])


def v11_continuity_boundary_hint(agent_type: str) -> str:
    """Explain V11's deterministic inherited/current state boundaries."""
    if not prompt_version_at_least("V11"):
        return ""
    guidance = {
        "planner": "把上一章交接状态写成 start_state 的继承事实，把本章新发生的变化写入 state_changes/end_state；历史权限范围不能代替当前权限状态。倒计时或帧再次出现时，必须明确是同一周期还是新周期。阶段性结论要同时写出范围和未知边界。",
        "writer": "先承接交接包中的上一章当前状态，再执行本章契约允许的新变化。历史授权、旧记录和原定窗口必须标为历史范围，不能写成当前可用权限；计数器重新从起点开始必须交代周期边界；阶段性结论不能扩展为最终因果。",
        "editor": "区分继承状态、本章新状态和历史状态。重点修复历史权限冒充当前权限、同一倒计时无说明重置、阶段性结论被写弱或写过界；局部措辞可直接修复，不要把普通表达问题升级成重写。",
        "validator": "把上一章当前状态、本章契约新状态和历史记录分别核对。历史权限/授权时长不等于当前权限；倒计时周期必须有明确承接或重启证据；阶段性结论既不能低于契约要求，也不能越过未知因果边界。",
        "extractor": "提取状态变化时保留 temporal_scope：inherited、current、historical 或 unknown。权限撤回、窗口关闭和计数器周期变化必须记录为不同状态，不要把历史范围沉淀为当前能力。",
    }
    return "\n\n【V11 状态边界与阶段性结论】\n" + guidance.get(agent_type, guidance["writer"])


def v12_evidence_surface_hint(agent_type: str) -> str:
    """Make source surfaces and post-closure observations explicit."""
    if not prompt_version_at_least("V12"):
        return ""
    guidance = {
        "planner": (
            "若本章涉及来源、回显、监测窗口或设备回执，必须分别规划读取路径、帧内来源字段、设备侧执行回执和实体影响；"
            "关闭执行登记后的新响应只能规划为保留只读监测列表中的观测。阶段性证据链必须明确为基于共同校准脉冲的报告级归并。"
        ),
        "writer": (
            "来源相关句子必须拆成四个面：读取来源登记为……；帧内来源字段为……；设备侧执行回执为……；实体影响为未知或有直接反馈。"
            "关闭执行登记完成后，固定写清‘保留的只读监测列表中出现新响应，状态仍为关闭，控制链未重新开放’。"
            "阶段性结论使用‘基于共同校准脉冲形成的阶段性报告结论’，只说明证据链归并或结构/周期对应，不确认同源、因果、归属、发送者或操作者。"
        ),
        "editor": (
            "局部修订时优先拆开读取路径、帧内来源字段、设备侧回执和实体影响；把关闭后的新响应补成只读监测观测，并明确控制链未重新开放。"
            "把‘同一异常事件链’前的表达收束为基于共同校准脉冲的阶段性报告归并，不增加同源或因果含义。"
        ),
        "validator": (
            "若正文把读取路径写成帧内来源字段，或把空来源字段补成读取窗口来源，报告 consistency 硬问题并引用两处正文。"
            "关闭执行登记后出现响应时，必须确认它位于保留的只读监测列表中且控制链未重新开放。"
            "阶段性证据链必须有共同校准脉冲和‘仅为报告级归并/结构对应’限定；否则不得升级为同源、因果、归属、发送者或操作者事实。"
        ),
        "extractor": (
            "沉淀证据时分别保存 read_path_source、frame_source_field、device_execution_source 和 physical_effect；"
            "关闭后只读监测中的响应保持 observation/unknown，不生成重新开放、实体执行或来源确认事实。"
        ),
    }
    # Ariadne A7+ 的契约卫生规则：交接包没有证据时，不要让 Writer 凭空造一个
    # 阶段性校准主张。A28 >= 7，因此这在 A28/V43 复现下生效；A7 以下的历史
    # 实验仍走完整版。
    if ariadne_series_at_least(7):
        guidance["planner"] = guidance["planner"].split("阶段性证据链", 1)[0]
        guidance["writer"] = guidance["writer"].split("阶段性结论", 1)[0]
        guidance["editor"] = guidance["editor"].split("把‘同一异常事件链’", 1)[0]
        guidance["validator"] = guidance["validator"].split("阶段性证据链", 1)[0]
    return "\n\n【V12 证据表面与关闭后观测边界】\n" + guidance.get(agent_type, guidance["writer"])


def v13_narrative_density_hint(agent_type: str) -> str:
    """Keep technical scenes readable and make character changes observable."""
    if not prompt_version_at_least("V13"):
        return ""
    guidance = {
        "planner": (
            "每个关键角色在本章至少规划一个可观察的反应、目标变化或选择；"
            "技术核验必须绑定人物关系、风险判断或行动后果，不要只列字段和说明。"
        ),
        "writer": (
            "每个关键角色必须通过动作、感官反应、对白、回避或选择表现本章状态变化；"
            "技术字段集中出现后，下一段优先用人物行动、冲突、感官或关系变化推进。"
            "同一字段只解释一次，禁止用连续的登记句代替人物选择；每个技术段落都要回答‘谁因此做了什么’。"
        ),
        "editor": (
            "优先压缩重复的字段登记、解释性复述和说明书式收束，补足与证据直接相关的人物动作或选择；"
            "不得为了增加情绪而改变角色卡、章节契约或证据边界。局部文风和人物反应问题直接修复，不退回 Writer。"
        ),
        "validator": (
            "检查关键角色是否有可观察的反应、目标或选择变化，以及技术字段是否连续堆叠而没有行动后果；"
            "这些属于 writing_quality/character_portrayal 的提示项，除非同时造成契约、事实或连续性冲突，不得触发内容重试。"
        ),
        "extractor": (
            "只提取正文明确表现的人物目标、情绪、关系或选择变化，并保留 source_chapter；"
            "技术字段重复登记不生成新的记忆事实，只有与人物行动或状态变化直接相关的内容才沉淀。"
        ),
    }
    return "\n\n【V13 人物反应与叙事信息密度】\n" + guidance.get(agent_type, guidance["writer"])


def v14_continuity_language_hint(agent_type: str) -> str:
    """Keep evidence terminology distinct and end chapters with action."""
    if not prompt_version_at_least("V14"):
        return ""
    guidance = {
        "planner": (
            "规划来源证据时必须分别命名‘来源元数据字段’与‘帧内来源字段’，二者不得使用同一个空泛的‘来源字段’代称；"
            "章节结尾必须规划一个角色可执行的下一步动作、承担的代价或关系变化，不以作者式总结句收束。"
        ),
        "writer": (
            "来源元数据字段只表示读取记录外部附带的来源信息；帧内来源字段只表示帧内容内部的来源值，二者必须使用完整、稳定的名称，"
            "不得把一个写成‘为空’后又把另一个残缺值简称为‘来源为空’。"
            "章节结尾必须落在角色已经做出的动作、明确选择、承担的代价或关系变化上；禁止使用‘本章说明’、‘下一章必须’、‘因此可知’、‘调查将继续’等作者式报告收束。"
            "最后一段至少包含一个可观察的行动结果或人物反应，不用连续的字段登记句代替结尾。"
        ),
        "editor": (
            "逐句统一‘来源元数据字段’和‘帧内来源字段’的术语；若正文确实分别存在两种状态，不得把其中一个改写成另一个。"
            "优先把说明书式结尾改成正文内角色动作、选择、代价或关系变化；删除作者式章节预告和结论，不改变事实边界。"
        ),
        "validator": (
            "检查来源元数据字段与帧内来源字段是否被明确区分；若同一表述让一个字段同时‘为空’又有残缺值，报告具体术语歧义。"
            "检查结尾是否由角色行动、选择、代价或关系变化落地；作者式总结只作为文风问题，除非同时造成契约或事实冲突，不得单独触发内容重试。"
        ),
        "extractor": (
            "沉淀证据时分别保存 source_metadata_field 和 frame_source_field；空值与残缺值必须保留在各自字段，不合并成模糊的‘来源为空’。"
            "提取章节结尾时优先记录实际发生的角色动作、选择、代价和关系变化，不把作者式总结句沉淀为剧情事实。"
        ),
    }
    return "\n\n【V14 证据术语与行动收束】\n" + guidance.get(agent_type, guidance["writer"])


def v15_compact_evidence_and_character_action_hint(agent_type: str) -> str:
    """Use a compact evidence checklist and observable relationship actions."""
    if not prompt_version_at_least("V15"):
        return ""
    guidance = {
        "planner": (
            "把来源证据压缩成同一份四项清单：来源元数据字段、帧内来源字段、设备侧执行回执、实体影响；"
            "每项只给一个状态和一个证明范围，不要在多个字段中重复同一结论。"
            "每章至少规划一组‘角色目标 -> 明确选择 -> 关系或行动后果’，后果必须能在正文中观察到。"
        ),
        "writer": (
            "涉及来源时只按四项清单落笔：来源元数据字段 / 帧内来源字段 / 设备侧执行回执 / 实体影响；"
            "每项只写一次，缺失就写未知或待核对，不用额外解释堆叠。"
            "每章至少让一个关键角色完成‘目标、选择、后果’三步，并让选择改变关系、权限、信任或下一步行动；"
            "不要用报告或字段登记替代人物之间的回应。"
        ),
        "editor": (
            "将来源信息整理为四项最小清单，删除重复登记和同义解释；除非四项之间造成事实冲突，局部缺失只补最短明确句。"
            "优先补足角色选择后的关系、权限、信任或行动后果，不新增无证据的心理动机或情节。"
        ),
        "validator": (
            "先检查四项最小证据清单是否各自有状态和证明范围；重复、冗余或单纯文风问题只列 warning，不触发内容重试。"
            "只有字段互相矛盾、实体影响被确认化或章节契约缺少关键证据时才阻断。"
            "同时检查至少一名关键角色是否完成目标、选择和可观察后果；缺少层次属于质量提示，除非违反契约不得单独阻断。"
        ),
        "extractor": (
            "只沉淀四项证据清单中的明确状态，字段缺失保持 unknown，不因重复描述生成新事实。"
            "优先沉淀正文明确发生的角色目标、选择、关系或行动后果，并保留 source_chapter。"
        ),
    }
    return "\n\n【V15 最小证据清单与关系动作】\n" + guidance.get(agent_type, guidance["writer"])


def v20_low_retry_state_hint(agent_type: str) -> str:
    """Keep V19 state protection without turning every omission into a rewrite."""
    if not prompt_version_at_least("V20"):
        return ""
    guidance = {
        "planner": "只输出上一章状态的短交接：窗口状态、倒计时状态、原件/副本状态。缺少证据字段时规划核对动作，不编造字段值。",
        "writer": "先承接窗口、倒计时和原件/副本三项状态。证据清单缺一项属于待核对信息，可用人物行动自然补足；只有与已接受事实或章节契约冲突时才改写状态。",
        "editor": "优先局部修复窗口状态、倒计时和原件/副本措辞。证据术语遗漏、重复登记和轻微说明书感直接修复，不要求 Writer 重写。",
        "validator": "只有硬事实、物品状态、时间线、核心事件或章节承接冲突才阻断；来源字段缺失、重复登记和可局部修复的证据措辞只能列 warning。",
        "extractor": "沉淀窗口状态、倒计时状态和原件/副本状态；证据字段缺失保持 unknown，不把观察升级为 accepted 事实。",
    }
    return "\n\n【V20 低重试跨章状态边界】\n" + guidance.get(agent_type, guidance["writer"])


def v21_numeric_and_cache_boundary_hint(agent_type: str) -> str:
    """Prevent deterministic countdown and post-power-loss state contradictions."""
    if not prompt_version_at_least("V21"):
        return ""
    guidance = {
        "planner": "所有倒计时必须与正文时间戳保持可计算一致；数字一致时不得规划成存在差异。主电源关闭后，只能规划蓄电池保留的只读同步队列观测，禁止写成待执行、继续动作或控制链重新开放。",
        "writer": "写出倒计时和时间戳后，按真实经过时间做算术核对；数字一致时只能写‘暂时同步’，不得写‘差出一截’。断电后的备用终端只能显示断电前写入蓄电池缓存的只读同步队列；使用‘待同步记录中的节点’，并明确这不代表控制链重新开放或实体动作继续。",
        "editor": "优先局部修正倒计时与时间戳的算术关系，以及断电后队列的证据边界。将‘待执行节点’改为‘待同步记录中的节点’，补充只读缓存限定；不为这类局部问题要求 Writer 重写。",
        "validator": "确定性核对倒计时数字与时间戳的差值：数值相等时，‘存在差异’属于硬时间线矛盾。断电后出现的队列必须明确来自蓄电池只读缓存，且不能表示控制链开放或实体动作继续；缺少这一限定时阻断。",
        "extractor": "将断电后队列沉淀为只读缓存中的待同步记录，不沉淀为待执行动作、重新授权或实体影响。倒计时只在时间戳可核对时记录为确定状态，否则保留 unknown。",
    }
    return "\n\n【V21 数值时间线与断电缓存边界】\n" + guidance.get(agent_type, guidance["writer"])


def v22_single_countdown_hint(agent_type: str) -> str:
    if not prompt_version_at_least("V22"):
        return ""
    guidance = {
        "planner": "同一章节同一倒计时周期只规划一个精确数值；后续写‘继续递减’或事件推进。新的精确数值必须明确标注重置、校准或新周期。",
        "writer": "同一章节只使用一个精确倒计时数值；之后不要创造第二个数字，写‘倒计时继续递减’或用事件时间推进。只有明确发生重置、校准或新周期时才能写新的精确值。",
        "editor": "删除同一倒计时周期中重复的精确数字，保留首个可核对值，后续改为‘继续递减’；不要把确定性数字卫生升级为 Writer 重写。",
        "validator": "同一倒计时周期出现多个精确数值时，必须核对是否有明确重置、校准或新周期说明；没有说明则阻断。",
        "extractor": "同一倒计时周期只沉淀首个可核对精确值，后续沉淀为继续递减；只有明确新周期才记录新值。",
    }
    return "\n\n【V22 单一精确倒计时规则】\n" + guidance.get(agent_type, guidance["writer"])


def v23_temporal_anchor_hint(agent_type: str) -> str:
    if not prompt_version_at_least("V23"):
        return ""
    guidance = {
        "planner": "没有结构化时间表时，精确时刻与精确‘X分钟后/前’不能同时规划；保留精确时刻，时长只写随后或一段时间。",
        "writer": "没有契约提供可核对映射时，不要在两个精确时刻之间写精确‘X分钟后/前’；保留时间戳，改用‘随后’或‘过了一会儿’。",
        "editor": "局部修正绝对时刻与相对时长冲突；没有可核对映射时，将精确‘X分钟后/前’改为‘随后’，不触发 Writer 重写。",
        "validator": "绝对时刻与相对分钟数只有在算术一致或契约明确校准时才可共存；否则判为时间线硬冲突。",
        "extractor": "只沉淀可由两个确定时间戳或章节契约直接计算的时长；无法计算时保持 unknown。",
    }
    return "\n\n【V23 时间锚点互斥规则】\n" + guidance.get(agent_type, guidance["writer"])


def v24_inherited_state_hint(agent_type: str) -> str:
    if not prompt_version_at_least("V24"):
        return ""
    guidance = {
        "planner": (
            "交接包 inherited_state 是本章开场已经成立的当前状态；先把它放入继承状态，"
            "再只规划本章真正发生的变化。不要把‘从上一章已显示为 X 变成 X’写成新事件；"
            "只有明确的本章动作、撤回、转移、重置或新周期才能改变 inherited_state。"
        ),
        "writer": (
            "开场先承接 inherited_state 中标为 inherited_current 的状态。"
            "如果某个编号、目标、封条、权限或设备状态已经在上一章确认，当前章只能写‘仍保持/继续显示/尚未改变’，"
            "除非正文明确发生新的动作、撤回、转移、重置或新周期；不要把状态复述写成状态变化。"
        ),
        "editor": (
            "对照 handoff.inherited_state 与正文，局部把‘已继承状态再次变化’改成‘仍保持/继续显示’。"
            "只有正文确实发生新动作、撤回、转移、重置或新周期，才保留变化叙述；不要因普通状态复述退回 Writer。"
        ),
        "validator": (
            "先核对 handoff.inherited_state：上一章已经成立的状态在本章被写成再次变化属于连续性问题，"
            "但若正文明确给出新动作、撤回、转移、重置或新周期，则不判冲突。报告时区分 inherited 状态、当前变化证据和历史状态。"
        ),
        "extractor": (
            "将上一章已经成立且本章未改变的内容标为 inherited_current，不生成重复的 state_change。"
            "只有正文明确发生新动作、撤回、转移、重置或新周期，才提取为 current change。"
        ),
    }
    return "\n\n【V24 继承状态与本章变化边界】\n" + guidance.get(agent_type, guidance["writer"])


def v25_artifact_boundary_hint(agent_type: str) -> str:
    """Make missing item ledgers and closed read-only windows executable."""
    if not prompt_version_at_least("V25"):
        return ""
    guidance = {
        "planner": (
            "先读取 item_state_ledger；账本为空时，本章不得规划新增纸张、记录页、原件、副本、附件、工具或持有者。"
            "需要记录证据时，只规划界面内记录、口述复述、纯观察或已在场设备上的读取动作。"
            "上一章已关闭的读取窗口只能规划展开仍保留的只读列表，不得规划重新点开、重新开启或设备主动响应。"
        ),
        "writer": (
            "item_state_ledger 是实体物品的唯一事实来源；账本为空或未列出的纸张、记录页、原件、副本、附件、工具和持有者都不得写入正文。"
            "记录证据请使用界面内记录、口述复述、纯观察或已在场设备，不要用‘取出记录页’等替代动作。"
            "已关闭的读取窗口只能写展开、查看仍保留的只读监测列表，不能写重新点开、重新开启或新的设备主动响应。"
        ),
        "editor": (
            "对照 item_state_ledger 删除未登记的纸张、记录页、原件、副本、附件、工具和持有者描写，改为界面内记录、口述或观察。"
            "将‘重新点开/重新开启受限读取’局部改为‘展开仍保留的只读监测列表’，不得改变已确认事实。"
        ),
        "validator": (
            "item_state_ledger 为空或未列出某实体时，正文确认该物品、持有者、转移或操作属于硬 item_state 冲突；"
            "已关闭窗口被写成重新点开、重新开启或设备主动响应属于硬连续性冲突。"
            "若正文只写界面内记录、口述复述、纯观察或展开既有只读列表，不得误判为新增物品或重新授权。"
        ),
        "extractor": (
            "只从 item_state_ledger 或正文明确且契约允许的动作中沉淀物品状态；未登记的纸张、记录页、原件、副本、附件和工具不要进入 accepted 状态。"
            "关闭窗口后的展开只读列表仍记录为只读观察，不记录为重新开启、设备主动响应或新授权。"
        ),
    }
    return "\n\n【V25 未登记实体与只读窗口边界】\n" + guidance.get(agent_type, guidance["writer"])


def v27_narrative_first_hint(agent_type: str) -> str:
    """Keep hard continuity rules while removing report-like prose pressure."""
    if not prompt_version_at_least("V27"):
        return ""
    guidance = {
        "planner": (
            "连续性契约是幕后约束，不是正文目录。优先设计可视化场景、角色目标、选择和后果；"
            "除非交接包或用户设定明确提供证据账本，否则不要主动创造来源字段、设备回执、记录页、"
            "读取者标记或四项证据清单。未知信息只规划观察、追问或调查动作，不用技术术语填满空白。"
        ),
        "writer": (
            "先写自然、可读的小说场景，再在不越过硬边界的前提下承接契约。交接包、记忆和章节契约是幕后约束，"
            "不是要求正文逐项复述的报告模板。除非大纲明确要求角色看到某个字段，否则不要在正文中输出‘来源元数据字段’、"
            "‘设备侧执行回执’、‘实体影响’、账本名称或审计式清单。未知信息用人物的观察、迟疑、对话和行动限制表现；"
            "不要连续解释同一个未知结论。每个场景都要有行动或选择，并产生可观察的情绪、关系或下一步后果。"
        ),
        "editor": (
            "把说明书式字段清单、重复的未知边界和审计口吻局部改写为场景中的动作、感官、对白或选择；"
            "不改变契约、硬事实、物品状态和伏笔边界。证据表面缺失本身不是重写理由。"
        ),
        "validator": (
            "只有输入中明确存在的证据账本、契约事件或正文可见字段才需要核对证据表面；缺少证据清单不等于失败。"
            "说明书式表达、技术重复和人物反应不足只记录为质量提示，除非同时造成硬事实或章节契约冲突，不得触发重写。"
        ),
        "extractor": (
            "后台可以结构化记录证据和状态，但只从正文明确发生的内容提取；不要因为正文没有审计式字段清单而补造证据。"
        ),
    }
    return "\n\n【V27 叙事优先与后台边界】\n" + guidance.get(agent_type, guidance["writer"])


def v28_action_ownership_hint(agent_type: str) -> str:
    """Keep read-only UI observations from becoming physical actions."""
    if not prompt_version_at_least("V28"):
        return ""
    guidance = {
        "planner": (
            "只读界面的显示、确认或有限读取不等于控制链执行，也不能直接改变门、设备、权限或实体状态。"
            "如果剧情需要进入或移动，必须把动作归属于角色的明确物理尝试，或把状态变化保留为来源未知的观察；"
            "不要把‘点击确认’规划成设备开门、授权或执行。"
        ),
        "writer": (
            "严格区分界面动作与实体动作：读取、展开、确认或接受历史内容只能改变可见信息，不能让设备开门、授权、"
            "启动控制链或产生实体影响。需要进入时，明确写成林默推、拉、迈步尝试等角色动作；若门缝或状态变化的机制未知，"
            "只写观察到的变化并保留未知，不把它归因于界面确认。"
        ),
        "editor": (
            "发现界面确认与实体变化被写成确定因果时，局部拆开动作归属：界面只显示结果，角色负责物理尝试，机制未知则保持未知；"
            "除非改变章节契约，否则直接修订，不要求泛化重写。"
        ),
        "validator": (
            "将‘读取/确认/展开界面’直接导致开门、授权、设备执行或实体影响视为硬动作归属冲突；"
            "若正文明确由角色物理尝试，或只保留未知的现场观察，则不得误判为设备执行。"
        ),
        "extractor": (
            "只有正文明确写出角色物理动作或直接实体反馈，才提取实体状态变化；界面确认本身不能沉淀为设备执行、授权或物品变化。"
        ),
    }
    return "\n\n【V28 动作归属与只读界面边界】\n" + guidance.get(agent_type, guidance["writer"])


def v29_compact_narrative_hint(agent_type: str) -> str:
    """Replace accumulated generation hints with one compact execution rule."""
    if not prompt_version_at_least("V29"):
        return ""
    guidance = {
        "planner": (
            "把上一章交接包和本章契约当作执行边界，不要在大纲中复述后台规则。"
            "本章只规划少量有因果的场景：角色目标、明确动作或选择、可观察后果；"
            "未知内容只规划观察、尝试、追问或调查，不用技术字段填充空白。"
        ),
        "writer": (
            "交接包和章节契约是幕后执行简报，不是正文目录。先写角色正在做什么、为什么做、"
            "做完后现场或关系发生了什么；每个场景都要有动作、选择或阻力。"
            "不要复述账本、权威等级、未知边界、来源字段或校验规则。"
            "界面读取只改变可见信息，实体变化必须来自角色明确动作或保持未知；不要为了证明合规而重复解释同一结论。"
        ),
        "editor": (
            "优先保留自然叙事和人物行动，只局部修复硬事实、章节契约或动作归属问题。"
            "不要为了补齐后台字段、权威等级或审计术语而改写正文，也不要新增正文没有的事实。"
        ),
        "validator": (
            "只阻断硬事实、时间线、角色状态、契约核心事件和动作归属冲突。"
            "说明书式表达、技术重复和人物反应不足记录为质量问题，不单独触发重写。"
        ),
        "extractor": (
            "只提取正文明确发生的动作、状态变化和伏笔推进；观察、猜测和未知保持原有不确定性，"
            "不要因为正文没有后台字段而补造记忆。"
        ),
    }
    return "\n\n【V29 精简叙事执行边界】\n" + guidance.get(agent_type, guidance["writer"])


def v31_evidence_ordered_continuity_hint(agent_type: str) -> str:
    """Order continuity execution and keep observations from becoming claims."""
    if not prompt_version_at_least("V31"):
        return ""
    guidance = {
        "planner": (
            "按四栏规划本章：先写 continuity_from_previous 中已经观察到的继承状态，"
            "再写 required_events 中角色可以执行的动作或核验，"
            "把未知关系放入 uncertain_events，最后在 forbidden_deviations 明确禁止的结论。"
            "未校准的两个系统只能规划并列观察、对照或调查，不能规划实际先后、因果、来源、身份或控制结论。"
        ),
        "writer": (
            "严格按‘承接可观察状态 -> 角色做出动作/选择 -> 展示现场后果’推进。"
            "对于未校准系统、同步声响、相邻记录或相似文字，只能写观察到的并列/近乎同步和人物无法判断；"
            "不得把它写成‘导致、因此、随后、先后、早于、晚于、证明、来自、就是’等实际因果、时间、来源或身份结论。"
            "unknown 是写作边界，不是要求正文反复解释的清单；保留未知时用最短的动作、迟疑或调查选择表现。"
        ),
        "editor": (
            "先判断问题是事件错误还是观察措辞越界。若场景动作和契约事件成立，只把越界的最小句子/从句改成"
            "并列观察、近乎同步、无法判断或待核对，保留角色动作、现场结果和未知边界。"
            "‘导致、因此、随后、先后、早于、晚于、证明、来自、就是’在没有直接证据时属于局部连续性措辞问题，"
            "优先写入 edited_content 修复，不要仅因这些词要求 Writer 泛化重写。"
        ),
        "validator": (
            "先检查正文是否真的完成契约事件，再检查观察是否被升级为结论。"
            "未校准系统中的实际先后、因果、来源、身份或控制断言仍属于硬冲突；"
            "如果问题只涉及一个可局部改写的连接词，明确引用最小正文证据，供 Editor 修复，不扩展成新的剧情要求。"
        ),
        "extractor": (
            "按‘观察内容、角色动作、可见结果、未知关系’分别沉淀。"
            "相邻或同步不提取为先后、因果、来源、身份或控制事实；保留 observation/unknown 和 source_chapter。"
        ),
    }
    return "\n\n【V31 证据顺序与局部连续性修复】\n" + guidance.get(agent_type, guidance["writer"])


def v44_compact_input_surface_hint(agent_type: str = "writer") -> str:
    """Keep V44 prompts executable without repeating audit-only context."""
    if not prompt_version_at_least("V44"):
        return ""
    guidance = {
        "planner": "只读取当前章节所需的已接受事实、上一章交接和角色摘要；不要把空旧字段或审计历史当作剧情输入。",
        "writer": "只读取叙事执行简报、当前角色状态、已接受事实和章节动作；不要逐项复述来源、权限、证据或审计字段。",
        "editor": "只核对正文、章节动作、终态、已接受事实和角色状态；空旧字段与重复契约不是新的证据。",
        "validator": "只用正文、章节契约、交接包和已接受事实判定硬冲突；候选线索和重复审计字段不能单独阻断。",
        "extractor": "只沉淀正文中新发生的可观察变化；不要重复写入交接包、角色卡和分层记忆已有的同一状态。",
    }
    return "\n\n【V44 输入面压缩与上下文所有权】\n" + guidance.get(agent_type, guidance["writer"])


def v45_narrative_delta_hint(agent_type: str = "writer") -> str:
    """Keep each chapter moving while preserving V44's bounded prompt surface."""
    if not prompt_version_at_least("V45"):
        return ""
    guidance = {
        "planner": (
            "本章最多规划三个主要节拍；每个节拍必须形成‘角色选择或动作 -> 阻力/新信息 -> 可见后果’。"
            "重复查询只有在带来新差异、代价或关系变化时才保留；至少安排一个与角色目标或风险直接相关的选择，"
            "结尾必须改变角色位置、决定、风险或调查问题。未知关系只能规划观察、假设或调查，不能规划为确认事实；"
            "记录信息优先使用界面、口述或纯观察，未登记的纸张、笔、笔记本等实体不得凭空加入。"
        ),
        "writer": (
            "【V45 单次证据与角色增量】同一屏幕、回执或线索只完整呈现一次，后续只写真正新增的差异、代价或选择。"
            "每个场景都要让角色因目标或风险做出一个可观察选择，并呈现选择带来的现场、关系或下一步变化。"
            "不要连续解释‘确认/意识到/无法判断’同一结论，也不要把交接包、契约或记忆字段改写进正文。"
            "界面显示、设备响应和人物猜测不能写成已确认的历史、身份、来源或因果；记录信息默认写成界面内记录、口述或观察，"
            "物品账本未登记时禁止新增纸张、笔、笔记本、文件夹或副本。"
        ),
        "editor": (
            "将重复的查询、解释和审计式总结合并为一次证据加一次角色反应；保留章节契约要求的动作和结尾增量。"
            "人物反应、节奏或局部措辞问题直接在 edited_content 中修复，只有硬事实、核心事件缺失或结构断裂才允许 rewrite。"
            "局部修复时不得把观察或假设升级为身份、来源、因果或历史事实；发现未登记的记录物品时改为界面记录、口述或观察。"
        ),
        "validator": (
            "检查每个核心节拍是否有角色动作/选择、阻力或新信息、可见后果，以及结尾是否发生状态增量。"
            "重复说明、人物反应单薄或节奏问题只能记录为 warning，不得单独触发重写；仍须阻断硬事实、时间线、角色状态和核心事件冲突。"
            "必须阻断未登记的纸张、笔、笔记本等记录物品，以及把 observed/tentative 写成已确认的身份、来源、因果或历史。"
        ),
        "extractor": (
            "每个记忆键只沉淀本章一次真实增量：新动作、状态变化、伏笔推进或明确的未决问题。"
            "同一证据的重复描述、继承状态和人物解释不重复生成 atom 或 progress；未知仍保持 candidate/unknown。"
            "记录动作本身不是新物品，未登记的纸张、笔、笔记本等不得沉淀为 accepted 状态；观察、假设和调查保持分层。"
        ),
    }
    return v44_compact_input_surface_hint(agent_type) + "\n\n【V45 单次证据与叙事增量】\n" + guidance.get(agent_type, guidance["writer"])


def v46_dramatic_turn_hint(agent_type: str = "writer") -> str:
    """Give each agent one shared character-driven scene spine."""
    if not prompt_version_at_least("V46"):
        return ""
    guidance = {
        "planner": (
            "【V46 戏剧转折】每章只设一个主导角色目标，并明确目标受到的阻力、角色必须做出的选择和选择造成的可见后果。"
            "beats 最多三个，按‘行动/选择 -> 阻力或代价 -> 后果’组织；重复查询、确认或读取必须合并，不能把字段变化冒充剧情推进。"
            "若信息仍未知，只能让角色改变策略、位置、风险或下一步目标，不能把未知答案写成确认事实。"
        ),
        "writer": (
            "【V46 戏剧转折】把本章的 dramatic_turn 当作场景脊柱：先让角色追求具体目标，再让阻力迫使其选择，最后展示选择带来的现场、关系、风险或下一步变化。"
            "不要逐项解释目标、阻力和后果，也不要用连续查询代替选择；同一证据只完整呈现一次。"
            "在不新增未登记物品、地点、身份或机制的前提下，让人物的动作、犹豫、让步或承担代价成为推进来源；观察和猜测仍须保持不确定。"
        ),
        "editor": (
            "【V46 戏剧转折】审阅时优先保留一条清晰的目标—阻力—选择—后果链。"
            "重复查询、解释和界面反馈应合并；人物动作、反应和局部节奏问题直接在 edited_content 修复。"
            "不要为了增加戏剧性新增角色、物品、地点、身份、因果或不可逆结果；硬事实和边界冲突仍按原规则处理。"
        ),
        "validator": (
            "【V46 戏剧转折】检查正文是否大体落地 dramatic_turn 的目标、阻力、选择和可见后果。"
            "缺少人物层次、重复操作或节奏平直只能作为 warning，不能单独触发 Writer 重写；硬事实、时间线、地点、物品、角色状态和核心事件冲突仍必须阻断。"
            "观察、假设和调查不得被写成确认身份、来源、意图或因果，‘戏剧转折’不能覆盖这些硬边界。"
        ),
        "extractor": (
            "【V46 戏剧转折】沉淀本章真正形成的角色选择及其可见后果，并与事实、场景和伏笔变化分开。"
            "重复查询、解释、继承状态和界面反馈不生成新记忆；未知选择结果保持 candidate/unknown，不升级为 accepted。"
        ),
    }
    return v45_narrative_delta_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v47_narrative_realization_hint(agent_type: str = "writer") -> str:
    """Turn the shared dramatic structure into concrete prose without adding facts."""
    if not prompt_version_at_least("V47"):
        return ""
    guidance = {
        "planner": (
            "【V47 叙事落地】每个主要节拍给 Writer 一个可见动作锚点和一个由已知状态支持的具体反应；"
            "不要新增心理标签、关系或未确认事实，也不要把目标、阻力和情绪写成抽象说明。"
        ),
        "writer": (
            "【V47 叙事落地】dramatic_turn 只作幕后路线，不要在正文解释目标、阻力、选择或情绪。"
            "把关键变化落成有限的可见动作、停顿、感官负担或关系反应；关键证据变化后最多保留一次人物回应，"
            "避免连续使用读取、记录、确认和‘这意味着’等解释句。只能使用角色卡或正文已经建立的性格与关系，"
            "用具体细节替代‘他意识到/他感到紧张’等总结，同时保留未知、观察和硬事实边界。"
        ),
        "editor": (
            "【V47 叙事落地】把抽象总结改成紧贴现有动作、感官或关系的局部句子，压缩重复的界面/记录说明。"
            "人物层次、节奏和措辞问题直接局部修复，不得为了增强戏剧性新增事实、关系、物品、动机或不可逆结果，"
            "也不得仅因文风问题要求 Writer 重写。"
        ),
        "validator": (
            "【V47 叙事落地】检查本章是否至少有一次与已知角色状态相符的可见回应；抽象、重复或感官不足只能作为 warning，"
            "不得单独触发 Writer 重写。只有事实、时间线、地点、物品、角色状态、核心事件等硬冲突才 block，"
            "且不得要求模型用新增设定补救。"
        ),
        "extractor": (
            "【V47 叙事落地】只沉淀正文明确发生的动作、状态变化和选择后果；不要把一次动作推断成新的性格、关系、动机或事实。"
            "人物反应的抽象评价、重复界面说明和未确认解释不生成 accepted 记忆。"
        ),
    }
    return v46_dramatic_turn_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v49_observation_language_hint(agent_type: str = "writer") -> str:
    """Keep interface observations from becoming historical or causal facts."""
    if not prompt_version_at_least("V49"):
        return ""
    guidance = {
        "planner": (
            "【V49 证据语言边界】界面标签、残缺片段和设备显示只能规划为可观察内容；"
            "不要把‘历史回执’规划成真实发生的历史记录，也不要预设发送者、原始请求或因果。"
            "未知推进必须使用‘是否/若确实存在/仍无法确认’这类调查表达。"
        ),
        "writer": (
            "【V49 证据语言边界】把界面内容写成‘显示/标注/可见片段’，不要写成设备承认真实存在、"
            "某人曾提交、某内容导致结果或某段历史已经发生。涉及发送者、原始请求和因果时必须保留‘是否/若确实/无法确认’；"
            "禁止用‘谁曾提交过’、‘什么内容让设备……’这类预设事实的问句替代未知边界。"
        ),
        "editor": (
            "【V49 证据语言边界】审阅时优先局部改写观察越界：把‘承认/确实存在/曾提交/导致’改为‘显示/标注/是否对应/仍无法确认’。"
            "只修正文措辞，不新增发送者、历史事件、原始请求或因果；这类局部语言问题不应要求 Writer 重写整章。"
        ),
        "validator": (
            "【V49 证据语言边界】严格阻止界面观察升级成历史、身份或因果事实，但将仅有此类措辞问题标记为可由 Editor 局部修复；"
            "只有同时改变已接受事实、时间线、地点、物品状态或核心事件时才触发 Writer 重写。"
        ),
        "extractor": (
            "【V49 证据语言边界】只记录界面明确显示的片段和正文明确发生的动作；不要把标签解释成真实历史、发送者、原始请求或因果。"
            "未知关系继续保持 unknown/candidate。"
        ),
    }
    return v47_narrative_realization_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v50_minimal_observation_patch_hint(agent_type: str = "writer") -> str:
    """Constrain observation-boundary repairs to the smallest possible edit."""
    if not prompt_version_at_least("V50"):
        return ""
    guidance = {
        "planner": (
            "【V50 最小证据修复】把界面观察、角色猜测和未知历史分开写。若需要推进，只规划一个可观察动作或调查问题；"
            "不要用完整问句预设发送者、原始请求、真实历史或因果已经存在。"
        ),
        "writer": (
            "【V50 最小证据修复】界面标签和残缺片段只能写成显示、标注或可见片段。"
            "若一句话不小心把观察升级成历史、身份、发送者、原始请求或因果，只改这一句，保留其余段落和动作不变；"
            "不得用新增事实、角色、地点、物品或机制补救。未知继续写成是否、若确实存在、仍无法确认。"
        ),
        "editor": (
            "【V50 最小证据修复】收到 Validator 指定的观察语言问题时，只替换 evidence 指向的最小句子，"
            "优先采用 fix_suggestion 的安全表达；除目标句外不得润色、重排或改动其他正文。"
            "不得新增发送者、原始请求、历史事件、因果、地点、物品、角色或机制；硬事实和契约冲突不能被局部降级。"
        ),
        "validator": (
            "【V50 最小证据修复】纯观察语言越界必须同时给出原句 evidence、未知边界 conflicts_with 和可直接采用的 fix_suggestion，"
            "并标记为可局部修复；若涉及已接受事实、时间线、地点、物品、角色状态或核心事件，必须保持 block，不能交给最小修复路径。"
        ),
        "extractor": (
            "【V50 最小证据修复】只从最终正文沉淀明确发生的动作和明确显示的片段。局部语言修复不产生新的历史、发送者、原始请求或因果事实；"
            "未知关系保持 candidate/unknown。"
        ),
    }
    return v49_observation_language_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v51_character_agency_hint(agent_type: str = "writer") -> str:
    """Ground one character choice in existing state without adding plot facts."""
    if not prompt_version_at_least("V51"):
        return ""
    guidance = {
        "planner": (
            "【V51 角色选择落地】在本章主导目标下只安排一个关键选择，并标明它依赖的已有角色卡约束、已经发生的状态或本章可见压力。"
            "选择必须改变行动、位置、暴露风险、时间成本或调查方向中的至少一项；不要凭空增加性格标签、动机、关系或过去经历。"
        ),
        "writer": (
            "【V51 角色选择落地】不要解释‘人物因为谨慎/愤怒/执着所以这样做’，而要让一个已有性格或已发生状态通过具体动作、犹豫、取舍或拒绝显出来。"
            "本章只突出一个关键选择，并让它带来可见的代价、风险、位置或下一步变化；不要用连续查询、重复确认和心理总结代替选择。"
            "选择只能使用角色卡和正文已建立的动机，不能新增身份、关系、能力、物品、地点或不可逆因果。"
        ),
        "editor": (
            "【V51 角色选择落地】优先保留一条‘已有约束/压力 -> 人物选择 -> 可见代价或方向变化’的动作链。"
            "把抽象性格说明、重复操作和心理结论压缩到最少，但不要为了显得有戏剧性新增动机、关系、事实或不可逆结果。"
            "人物层次和节奏是软质量问题，直接局部修复，不得单独触发 Writer 重写。"
        ),
        "validator": (
            "【V51 角色选择落地】检查本章是否有一个可从既有角色卡/已发生状态解释的关键选择，以及选择造成的可见变化。"
            "缺少人物纹理、选择不够鲜明或推进偏平只能作为 warning，不能单独触发 Writer 重写；事实、时间线、地点、物品、角色状态和核心事件冲突仍必须 block。"
        ),
        "extractor": (
            "【V51 角色选择落地】只沉淀正文明确发生的选择、动作和可见后果；不要把一次选择反推成新的性格、动机、关系或背景。"
            "如果选择结果仍未知，保留 candidate/unknown，不升级为 accepted。"
        ),
    }
    return v50_minimal_observation_patch_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v52_visible_consequence_chain_hint(agent_type: str = "writer") -> str:
    """Turn one grounded choice into a bounded action and visible consequence."""
    if not prompt_version_at_least("V52"):
        return ""
    guidance = {
        "planner": (
            "【V52 可见后果链】把 V51 的关键选择具体化为一条可执行的有限动作链：角色先为已有目标采取一次明确动作，"
            "动作必须得到一个正文可观察的现场响应，并让行动、位置、时间成本、暴露风险或调查策略至少有一项发生变化。"
            "dramatic_turn.choice 不得留空，也不得写成‘继续观察/等待变化’；如果没有合理的新动作，就收缩目标，不要用重复查询填充节拍。"
        ),
        "writer": (
            "【V52 可见后果链】把本章唯一选择写成‘有限动作 -> 现场响应 -> 新的策略/风险/代价’的连续场面。"
            "有限动作必须是角色实际做出的可观察行为，现场响应必须来自已建立的设备、地点、角色或事实；最后要让角色的下一步、位置、时间成本、暴露风险或调查方向出现可见变化。"
            "停留、等待、再次注视、重复点击、重复询问和心理总结不算选择或后果；不要为了制造变化新增角色、物品、地点、能力、身份、机制或不可逆因果。"
        ),
        "editor": (
            "【V52 可见后果链】检查并保留一条‘明确动作 -> 可观察响应 -> 可见变化’的最短叙事链。"
            "删掉把等待、注视、重复查询包装成推进的段落，以及重复解释同一未知信息的句子；不要新增事实，不要把软性人物不足升级成 Writer 重写。"
        ),
        "validator": (
            "【V52 可见后果链】检查本章是否存在一次明确的角色动作、一个正文可观察的响应，以及由此产生的行动/位置/时间成本/风险/调查方向变化。"
            "若只有等待、注视、重复查询或心理说明，把‘后果链不充分’列为 warning，不得单独触发 Writer 重写；事实、时间线、地点、物品、角色状态和核心事件冲突仍必须 block。"
        ),
        "extractor": (
            "【V52 可见后果链】只沉淀正文明确发生的动作、现场响应和可见变化；不要把计划中的动作、等待或心理解释写入记忆。"
            "如果响应的来源、因果或后续结果仍未知，保持 candidate/unknown，不升级为 accepted。"
        ),
    }
    return v51_character_agency_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v53_cross_chapter_stage_hint(agent_type: str = "writer") -> str:
    """Prevent replay of the previous chapter's completed terminal state."""
    if not prompt_version_at_least("V53"):
        return ""
    guidance = {
        "planner": (
            "【V53 跨章阶段账本】先读取交接包中的 completed_event_ledger 和 previous_terminal_state，"
            "把上一章已经完成的动作、现场响应和终态当作不可重复的已完成事项。必须输出非空 new_stage_delta，"
            "明确本章相对上一章新增的阶段、地点/调查入口、关系、位置或风险变化；不要把‘再次触碰/再次核对/再次停止’包装成阶段推进。"
        ),
        "writer": (
            "【V53 跨章阶段账本】上一章的 completed_event_ledger 和 previous_terminal_state 是已经发生的终态。"
            "开场只用最短篇幅承接结果，然后必须落到 new_stage_delta 指定的新阶段：新的地点或调查入口、关系变化、位置变化、风险变化或策略变化。"
            "不得完整重演上一章已经完成的动作和响应；如果必须回顾，只用一句结果性承接，并立即让角色采取新的行动。"
        ),
        "editor": (
            "【V53 跨章阶段账本】对照 completed_event_ledger、previous_terminal_state 和 new_stage_delta，"
            "删除上一章动作/响应的完整复演，保留最短承接句，并把正文落到新的阶段增量。纯重复或缺少阶段增量属于连续性质量问题；"
            "只有造成核心事件、硬事实、时间线、地点或角色状态冲突时才要求 Writer 重写。"
        ),
        "validator": (
            "【V53 跨章阶段账本】检查正文是否只是重复上一章的 completed_event_ledger 或停留在 previous_terminal_state，"
            "以及是否落实非空 new_stage_delta。完整复演上一章已完成动作/响应，或全章没有新阶段增量，报告具体重复证据并标为 continuity warning；"
            "若同时缺少章节核心事件或违反硬事实/时间线/地点/角色状态，仍必须 block。"
        ),
        "extractor": (
            "【V53 跨章阶段账本】按 new_stage_delta 只沉淀本章相对上一章真正新增的阶段、入口、关系、位置、风险或策略变化。"
            "completed_event_ledger 中的继承事项和重复复演标为 inherited/replayed，不生成新的进展记忆；只有正文明确的新变化才写入候选更新。"
        ),
    }
    return v52_visible_consequence_chain_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v54_intra_chapter_action_repair_hint(agent_type: str = "writer") -> str:
    """Prevent one chapter from replaying the same operation surface."""
    if not prompt_version_at_least("V54"):
        return ""
    if prompt_version_at_least("V66"):
        return v66_compact_character_texture_hint(agent_type)
    if prompt_version_at_least("V65"):
        return v65_evidence_boundary_hint(agent_type)
    if prompt_version_at_least("V64"):
        return v64_cross_chapter_stage_transition_hint(agent_type)
    if prompt_version_at_least("V63"):
        return v63_chapter_closure_hint(agent_type)
    if prompt_version_at_least("V62"):
        return v62_stage_breakthrough_hint(agent_type)
    if prompt_version_at_least("V61"):
        return v61_state_progression_hint(agent_type)
    if prompt_version_at_least("V60"):
        return v60_external_consequence_hint(agent_type)
    if prompt_version_at_least("V59"):
        return v59_action_first_realization_hint(agent_type)
    if prompt_version_at_least("V58"):
        return v58_structured_character_turn_hint(agent_type)
    if prompt_version_at_least("V57"):
        return v57_compact_character_surface_hint(agent_type)
    if prompt_version_at_least("V55"):
        if prompt_version_at_least("V56"):
            return v56_character_driven_tension_hint(agent_type)
        return v55_primary_action_turn_hint(agent_type)
    guidance = {
        "planner": (
            "【V54 章节内动作账本】输出 unique_action_ledger，只列本章真正需要执行的设备、查询、验证或进入操作；"
            "每个 operation 只能出现一次，并为它写一个可观察 response 和一个实际 change。不要把同一操作拆成‘再次提交/再次核对’来填充节拍。"
        ),
        "writer": (
            "【V54 章节内动作账本】严格按 unique_action_ledger 执行：一个 operation 只能执行一次，随后只能描写它已经产生的 response、"
            "角色选择或新的阶段变化，不得重新提交、重复点击、重复核对或重复询问同一操作。未知字段只写‘待判定’、‘未返回’或‘匹配结果为空’，"
            "不得把缺少返回写成‘不可见’等确定属性。"
        ),
        "editor": (
            "【V54 章节内动作账本】检查正文是否重复执行 unique_action_ledger 中的同一 operation，或把未知标签写成确定属性。"
            "只删除重复动作句、替换错误标签并保留第一次 response 和新阶段变化；不要新增事实、操作、角色或机制。"
        ),
        "validator": (
            "【V54 章节内动作账本】对照 unique_action_ledger 检查每个 operation 是否只执行一次。"
            "同一操作重复提交、重复查询和‘不可见’这类未知属性过度断言，必须提供 evidence、conflicts_with 和 fix_suggestion，标为可局部修复；"
            "若同时涉及已接受事实、时间线、地点、物品、角色状态或核心事件，仍必须 block。"
        ),
        "extractor": (
            "【V54 章节内动作账本】只沉淀每个 operation 的第一次明确 response 和实际新 change；重复提交、重复核对和局部修复不生成第二条进展。"
            "未知字段保持待判定/未返回和 candidate/unknown，不升级为确认事实。"
        ),
    }
    return v53_cross_chapter_stage_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v55_primary_action_turn_hint(agent_type: str = "writer") -> str:
    """Keep a chapter's procedural action in service of one character turn."""
    if not prompt_version_at_least("V55"):
        return ""
    guidance = {
        "planner": (
            "【V55 单一核心动作转折】输出 primary_action，必须包含 action、response、decision、cost_or_risk 和 new_stage。"
            "本章只规划一个真正改变角色选择、位置、风险、时间成本或调查方向的核心动作；设备/查询/验证只能作为该动作的一次性载体。"
            "若 response 只是信息回显，必须明确角色随后做出的 decision，不能用第二轮查询、确认或解释充当推进。"
        ),
        "writer": (
            "【V55 单一核心动作转折】围绕 primary_action 写一条完整链：角色做出一次 action，现场给出一次可观察 response，角色据此作出 decision 并承担明确的 cost_or_risk，落到 new_stage。"
            "同一场景后续只能观察、选择、移动或承受后果，不得再开一轮查询/确认/点击来填充篇幅。"
            "不要把界面字段、未知标签或解释性复述写成角色决策；unknown 仍只能写待判定、未返回或匹配结果为空。"
        ),
        "editor": (
            "【V55 单一核心动作转折】检查正文是否形成 action -> response -> decision/cost_or_risk -> new_stage。"
            "压缩第二轮查询、重复确认和无决策的解释段，保留第一次响应及角色真正选择；不得新增事实、机制、角色或场景。"
        ),
        "validator": (
            "【V55 单一核心动作转折】核对 primary_action 的 action、response、decision、cost_or_risk 和 new_stage 是否都在正文有对应证据。"
            "缺少人物决策或代价属于质量 warning，不单独触发 Writer 重试；若正文与章节契约、硬事实、时间线、地点、角色状态或核心事件冲突，才按硬问题处理。"
        ),
        "extractor": (
            "【V55 单一核心动作转折】只沉淀正文明确发生的核心 action、response、decision、cost_or_risk 和 new_stage。"
            "字段回显、重复确认、解释性复述和未发生的计划不生成新进展；未知来源、因果和属性保持 candidate/unknown。"
        ),
    }
    return v53_cross_chapter_stage_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v56_character_driven_tension_hint(agent_type: str = "writer") -> str:
    """Make the V55 action turn visibly belong to the character."""
    if not prompt_version_at_least("V56"):
        return ""
    guidance = {
        "planner": (
            "【V56 角色驱动转折】在 primary_action 之外输出 character_turn，包含 actor、goal、pressure、choice_basis、choice、personal_cost 和 state_change。"
            "goal、pressure 和 choice_basis 只能来自角色卡、上一章已发生状态或本章可见压力；角色卡为空时只使用已观察到的行为与状态，不得编造性格、背景、关系或能力。"
            "character_turn 解释‘为什么是这个角色在此刻作出这个选择’，不是再规划一套动作；pressure 必须具体，personal_cost 必须是人物实际失去、暴露或承担的东西。"
        ),
        "writer": (
            "【V56 角色驱动转折】把 character_turn 写进场景，而不是把字段名或心理分析写出来：先让现实压力逼近，再让角色基于已建立的目标/状态作出有取舍的选择，最后展示个人代价和新阶段。"
            "primary_action 只负责一次外部动作与现场响应；character_turn 负责这个角色为何拒绝、冒险、妥协或改变策略。技术提示、查询和设备反应最多用最短篇幅承载动作，不得成为章节主体。"
            "没有来源的性格、童年、关系、能力和动机禁止补写；若角色卡没有静态特征，就用已发生的选择、风险和当前目标体现人物，不要用‘他一向……’等空泛标签。"
        ),
        "editor": (
            "【V56 角色驱动转折】检查正文是否同时落地 primary_action 与 character_turn：外部动作只发生一次，人物选择必须能从既有目标/状态和具体压力解释，并造成个人代价或策略变化。"
            "压缩设备回显、重复查询和抽象心理说明，保留能证明角色取舍的动作、停顿、拒绝、承受或位置变化；不得新增性格、背景、关系、能力或因果。"
        ),
        "validator": (
            "【V56 角色驱动转折】核对 character_turn 的 goal、pressure、choice_basis、choice、personal_cost 和 state_change 是否在正文有证据，且来源属于角色卡、已发生状态或本章可见压力。"
            "人物纹理薄、代价不够鲜明或技术描写偏多只能是 warning，不得单独触发 Writer 重试；若新增或篡改硬事实、角色状态、时间线、地点、核心事件，仍按 block 处理。"
        ),
        "extractor": (
            "【V56 角色驱动转折】只沉淀正文明确发生的角色选择、现实压力、个人代价和状态变化；不要从一次动作反推新的性格、背景、关系、能力或长期动机。"
            "primary_action 的外部响应与 character_turn 的人物解释分开记录，未经正文证据的原因保持 candidate/unknown。"
        ),
    }
    return v55_primary_action_turn_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v57_compact_character_surface_hint(agent_type: str = "writer") -> str:
    """Keep the character turn, but remove the accumulated audit surface."""
    if not prompt_version_at_least("V57"):
        return ""
    guidance = {
        "planner": (
            "【V57 精简角色叙事】把本章规划成一场由具体压力逼出的角色选择，而不是设备操作清单。"
            "沿用 primary_action 和 character_turn 字段，但只选一个核心取舍：角色想得到什么、眼前压力是什么、"
            "两种选择各自失去什么、角色最终做了什么，以及现场因此出现的一个可见后果和新阶段。"
            "压力和代价必须来自角色当前状态、上一章已发生事实或本章可见场面；unknown/candidate 只能保持为观察、疑问或线索。"
            "不要用重复查询、确认或新增证据字段制造推进，不得新增未登记人物、物品、地点、身份、能力或机制。"
        ),
        "writer": (
            "【V57 精简角色叙事】只围绕一个场景转折写正文：现实压力先落到现场，角色做一次有取舍的动作，"
            "现场给出一次具体回应，角色承担代价并让位置、风险、关系、时间或调查方向发生可见变化。"
            "把 primary_action 和 character_turn 当作幕后路线，不要输出字段名、心理分析、契约、记忆或审计说明。"
            "用动作、停顿、感官细节和必要对话表现选择；不要连续读取、记录、确认、解释同一信息，也不要把界面显示或猜测写成历史、身份、因果或授权。"
            "没有静态角色卡时，用当前目标、已发生选择和眼前代价形成角色纹理，不写‘他一向’等空泛性格。"
            "不得新增未登记人物、物品、地点、身份、能力或机制；保留未知，不要为了制造戏剧性补全答案。"
        ),
        "editor": (
            "【V57 精简角色叙事】优先把正文修成一场清楚的角色转折：压力、一次动作、一次回应、一次取舍和一个可见后果。"
            "直接删减审计式复述、重复查询、连续否定句和抽象心理总结，保留第一次有效回应与角色承担的真实代价。"
            "只做局部文字和节奏修复，不新增事实、角色、物品、地点、机制或未知结论；人物纹理偏薄本身不触发重写。"
        ),
        "validator": (
            "【V57 精简角色叙事】检查正文是否有一个可追踪的场景转折：角色目标/压力、一次核心动作、现场回应、"
            "角色取舍/代价和新的可见状态。重复操作、审计腔或人物纹理偏薄只能记录为 warning，不单独触发 Writer 重写。"
            "只有与 accepted/published/user/frozen 事实、时间线、地点、物品、角色状态或核心事件冲突，或严重断章，才 block。"
            "unknown/candidate 仍不得被升级成身份、历史、因果、授权或机制事实。"
        ),
        "extractor": (
            "【V57 精简角色叙事】只沉淀正文明确发生的角色选择、压力、代价、现场回应和新状态。"
            "不要把写作中的心理解释、计划、重复操作或猜测写入 accepted 事实；未经正文证据的性格、动机、关系和因果保持 candidate/unknown。"
        ),
    }
    return guidance.get(agent_type, guidance["writer"])


def v58_structured_character_turn_hint(agent_type: str = "writer") -> str:
    """Require a usable shared turn before the compact narrative surface runs."""
    if not prompt_version_at_least("V58"):
        return ""
    guidance = {
        "planner": (
            "【V58 结构化角色转折】必须输出非空 primary_action 和 character_turn，供 Writer、Editor、Validator、Extractor 共用。"
            "primary_action 固定包含 action、response、decision、cost_or_risk、new_stage；character_turn 固定包含 actor、goal、pressure、"
            "choice_basis、choice、personal_cost、state_change。每个字段都要是具体短句，不能留空、写成‘待定’或只复制字段名。"
            "所有内容只能来自上一章已发生状态、角色卡、本章可见压力和本章大纲；不得为了填字段新增人物、物品、地点、身份、能力、机制或未知结论。"
            "两套对象必须描述同一个核心取舍：一个外部动作、一个现场回应、一个角色选择、一个可见代价和一个新阶段。"
        ),
        "writer": (
            "【V58 结构化角色转折】只围绕共享的 primary_action 和 character_turn 写一场完整转折：压力落地，角色做一次动作，现场给出回应，"
            "角色作出取舍并承担 personal_cost，最后让 position、risk、time、relationship 或 investigation_stage 出现一个可见变化。"
            "必须使用对象中的具体 decision/choice/cost/state_change，不要把字段名、契约、记忆或心理分析写进正文。"
            "禁止用连续追问、读取、记录、确认或等待填充篇幅；同一证据只完整呈现一次。unknown/candidate 仍只能是观察、疑问或调查线索。"
            "如果对象内容不足，优先写已有目标、眼前压力和已发生选择，不得自行补写性格、背景、关系、能力、身份、物品或机制。"
        ),
        "editor": (
            "【V58 结构化角色转折】核对正文是否落地同一套 primary_action 与 character_turn：动作、回应、选择、代价和新阶段必须各有可见证据。"
            "直接压缩重复查询、记录、确认、等待和解释性心理句，保留第一次有效回应与真实取舍；人物薄弱只能局部润色，不能因此触发 Writer 重写。"
            "不得新增事实、实体、机制或未知结论。"
        ),
        "validator": (
            "【V58 结构化角色转折】先核对 primary_action 与 character_turn 的字段是否非空且在正文有证据，再核对事实边界。"
            "缺少人物纹理、代价不够鲜明或存在审计腔只能 warning；只有硬设定、时间线、地点、物品、角色状态、核心事件冲突或严重断章才 block。"
            "不得把 unknown/candidate 升级为身份、历史、因果、授权或机制事实。"
        ),
        "extractor": (
            "【V58 结构化角色转折】只沉淀正文明确落地的 action、response、decision、choice、cost、state_change 和新阶段。"
            "字段缺失、计划、重复操作、心理推断和未知解释不得升级为 accepted；未经正文证据的性格、动机、关系和因果保持 candidate/unknown。"
        ),
    }
    return guidance.get(agent_type, guidance["writer"])


def v59_action_first_realization_hint(agent_type: str = "writer") -> str:
    """Make the shared turn read as a scene before it reads as an explanation."""
    if not prompt_version_at_least("V59"):
        return ""
    guidance = {
        "planner": (
            "【V59 先行动后解释】必须沿用 V58 的结构化输出：primary_action 和 character_turn 都必须是非空对象，不能输出字符串。"
            "primary_action 固定包含 action、response、decision、cost_or_risk、new_stage；character_turn 固定包含 actor、goal、pressure、"
            "choice_basis、choice、personal_cost、state_change。先把这两个对象规划成一个先发生、后解释的场景。"
            "核心 action 必须让角色在当前场面中做出一次可观察且会关闭至少一个选择的取舍；设备、查询或读取只能是动作载体，不能成为章节主体。"
            "先指定现场压力、角色选择和立即可见的 consequence，再安排最多一条信息揭示；不得用摘要、字段解释或连续追问代替选择。"
            "所有压力、代价、后果和未知边界仍必须来自已有状态、角色卡或本章可见材料，不得新增人物、物品、地点、身份、能力、机制或因果。"
        ),
        "writer": (
            "【V59 先行动后解释】把共享的 primary_action 和 character_turn写成场景，不要把它们翻译成报告。"
            "开场先让现场压力发生，随后让角色做一次会关闭某条退路、改变位置/风险/时间/调查方向的具体选择；选择的可见后果必须紧接着出现。"
            "只有在动作和后果之后，才呈现最多一条必要信息；禁止用读取、记录、确认、解释、等待或连续追问填充前半章。"
            "正文不输出字段名、契约、记忆或心理分析，不把未知线索写成答案；结尾落在新的可观察状态或现实代价上，不用抽象反问代替变化。"
            "不得新增未登记人物、物品、地点、身份、能力、机制或因果。"
        ),
        "editor": (
            "【V59 先行动后解释】检查正文顺序是否为现场压力 -> 角色选择 -> 立即后果 -> 必要信息 -> 新状态。"
            "把前置的摘要、界面说明、重复查询和抽象心理句压缩或后移；保留已有证据，不得为了制造动作新增事实、实体、机制或未知结论。"
            "如果人物纹理或文学表达偏薄，只做局部措辞和顺序修复，不触发 Writer 重写；只有硬冲突、核心事件缺失或严重断章才阻断。"
        ),
        "validator": (
            "【V59 先行动后解释】检查正文是否有可定位的现场压力、一次角色取舍、紧随其后的可见后果和新的终态。"
            "如果信息解释或界面操作先于人物选择、结尾只剩抽象提问，报告为 narrative warning，不单独触发 Writer 重试。"
            "仍须优先检查 accepted/published/user/frozen 事实、时间线、地点、物品、角色状态和核心事件；unknown/candidate 不得升级为确认事实。"
        ),
        "extractor": (
            "【V59 先行动后解释】只沉淀正文中实际发生的角色选择、可见后果、位置/风险/时间/调查方向变化和必要的新事实。"
            "不要把开场说明、字段解释、心理推断、计划或未发生的后果写入 accepted；未知原因和归属继续保持 candidate/unknown。"
        ),
    }
    return guidance.get(agent_type, guidance["writer"])


def v60_external_consequence_hint(agent_type: str = "writer") -> str:
    """Require the action-first turn to change the scene outside the interface."""
    if not prompt_version_at_least("V60"):
        return ""
    guidance = {
        "planner": (
            "【V60 界面外部后果】沿用 V59 的全部结构化对象和先行动后解释顺序，但立即后果不能只停留在屏幕、回执、提示音或信息新增。"
            "必须从已有场景事实中规划一个界面之外可观察的变化，例如位置、门窗/通道状态、可用物品、暴露风险、时间窗口、关系距离或调查方向；"
            "该变化要直接由 primary_action/character_turn 的选择引起，并让至少一条原有退路关闭。"
            "结尾必须是与上一章不同的具体终态，不能回到原位置、原风险和原选择；不得为了满足后果要求新增人物、物品、地点、身份、能力、机制或因果。"
        ),
        "writer": (
            "【V60 界面外部后果】沿用 V59 的全部结构化对象和先行动后解释顺序。角色选择后，必须在紧接的场景中展示一个界面之外的可观察后果："
            "身体位置、门窗/通道、手中物品、暴露风险、剩余时间、关系距离或调查方向至少有一项发生变化；屏幕文字或设备回执只能作为触发，不能算后果本身。"
            "结尾落在具体且不可原样退回的新状态，让读者能看见角色失去了哪条退路或承担了什么代价。只使用已有事实和本章契约允许的变化，不为制造动作补写实体、机制或答案。"
        ),
        "editor": (
            "【V60 界面外部后果】在 V59 顺序之外，核对角色选择是否真正改变了界面之外的可见状态。若正文只有屏幕反馈、回执或解释，"
            "优先局部压缩解释并突出正文已有的位置、风险、时间、物品、关系或调查方向变化；不得凭空新增事件、实体、机制或未知结论。"
            "终态应与开场不同；这类叙事不足只能局部修复，不单独触发 Writer 重写。"
        ),
        "validator": (
            "【V60 界面外部后果】除 V59 的压力、选择、即时后果和新终态外，检查后果是否在界面之外可观察。"
            "只有屏幕/回执/提示音变化而没有位置、风险、时间、物品、关系或调查方向变化，记录为 narrative warning，不单独触发 Writer 重试；"
            "若正文与章节契约、已接受事实、时间线、地点、物品或角色状态冲突，仍按硬冲突处理。"
        ),
        "extractor": (
            "【V60 界面外部后果】只沉淀正文明确发生的界面外状态变化，以及由该变化造成的位置、风险、时间、物品、关系或调查方向更新。"
            "屏幕回执、解释、计划和未发生的后果不能单独写成 accepted 状态；无法确认的原因和归属继续保持 candidate/unknown。"
        ),
    }
    return v59_action_first_realization_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v61_state_progression_hint(agent_type: str = "writer") -> str:
    """Keep evolving scene state distinct from repeated explanation or replacement."""
    if not prompt_version_at_least("V61"):
        return ""
    guidance = {
        "planner": (
            "【V61 状态演进收束】沿用 V60 的界面外部后果，但为本章只选一个明确的状态演进：起始状态 -> 角色选择 -> 外部变化 -> 终态。"
            "同一设备、门面或地点的后续状态是前一状态的演进，不要把它规划成重新建立一条规则；解释设备限制最多安排一次，后续用动作和新状态推进。"
            "终态必须具体写出角色所在位置、可用渠道、风险或调查方向中至少一项的新值，不能只写‘仍未知’或重复上一章结论。"
        ),
        "writer": (
            "【V61 状态演进收束】把同一对象的变化写成连续动作：先承接它原本的状态，再让角色选择导致状态改变，最后落在不可原样退回的终态。"
            "设备/回执限制只解释一次；后文不要反复说‘无法解释、无法继续读取、来源未知’，把篇幅交给位置、通道、风险、时间或调查方向的实际变化。"
            "本章结尾必须给出一个和开场不同的具体状态；不要用重复查询、重复确认或抽象疑问句收尾，也不要把状态演进写成规则被重新发明。"
        ),
        "editor": (
            "【V61 状态演进收束】优先压缩同一设备/地点限制的重复说明，只保留第一次必要解释；把正文已有的状态变化、位置移动、渠道丢失、风险或调查方向变化前置到可见动作之后。"
            "检查开场状态与结尾状态是否不同。不得为了修辞新增事实、机制、实体或未知结论；状态演进不足是局部叙事问题，不单独触发 Writer 重写。"
        ),
        "validator": (
            "【V61 状态演进收束】区分同一对象的后续观察与硬设定替换：设备从显示到熄灭、渠道从可用到暂时不可用属于状态演进，不能仅因表述变化判为冲突。"
            "仍须阻断真正的能力、地点、时间线、权限、角色状态或冻结事实矛盾。重复解释和终态不变记录为 narrative warning，不单独触发 Writer 重试。"
        ),
        "extractor": (
            "【V61 状态演进收束】同一设备、门面或地点在本章发生的显示、熄灭、关闭、失去渠道、位置或风险变化，按已有 memory key 记录为新的观察状态演进；不要新建重复规则。"
            "保留原有事实的来源和历史版本，不把状态演进写成推翻规则；只有明确改变能力、地点、权限、时间线或冻结标记才报告 high conflict。"
        ),
    }
    return v60_external_consequence_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v62_stage_breakthrough_hint(agent_type: str = "writer") -> str:
    """Turn a continuous scene into a concrete, evidence-bearing stage change."""
    if not prompt_version_at_least("V62"):
        return ""
    guidance = {
        "planner": (
            "【V62 阶段突破】沿用 V61 的状态演进，但本章的 new_stage 必须是信息性结果或真实代价，"
            "不能只写换一个站位、再次听见声响、继续观察、继续等待或再次确认未知。"
            "在已有事实和本章允许动作内，规划一次会改变可验证条件的选择：得到新的可观察证据、关闭一条现实退路、"
            "改变访问/关系/风险/时间窗口，或把调查问题缩小到一个更具体的待验证条件。"
            "若答案仍未知，也必须让未知因为本章行动而变得更具体，不能重复上一章的未知表述；不要新增人物、物品、地点、身份、能力、机制或因果。"
        ),
        "writer": (
            "【V62 阶段突破】沿用 V61 的状态演进，但 action -> response -> decision 之后，必须落到一个信息性结果或真实代价。"
            "仅移动到另一个观察位置、再次听见相似声响、继续等待、再次复述‘仍未知’，都不算阶段突破。"
            "让角色的选择至少带来一项可见变化：获得新的可观察证据、失去一条现实退路、改变访问/关系/风险/时间窗口，"
            "或把悬念收窄为一个新的具体待验证条件。答案可以继续未知，但未知必须因本章行动而更具体、更受约束。"
            "只使用已有事实和章节契约；不得为制造突破新增人物、物品、地点、身份、能力、机制或因果。"
        ),
        "editor": (
            "【V62 阶段突破】检查本章是否在共享转折之后产生信息性结果或真实代价。"
            "把单纯换站位、重复听声、重复等待、重复解释未知识别为 narrative warning，并在 edited_content 中压缩循环、"
            "突出正文已有的新证据、退路关闭、风险/时间/关系/访问变化或更具体的待验证条件。"
            "不得凭空新增事件、实体、机制或答案；只有硬事实、时间线、地点、角色状态、核心事件或严重断章问题才允许 rewrite。"
        ),
        "validator": (
            "【V62 阶段突破】除 V61 的起始状态、角色选择、外部变化和终态外，核对终态是否包含信息性结果或真实代价。"
            "单纯换站位、重复听声、重复等待、重复说未知或只改写观察角度，记录为 narrative warning，不单独触发 Writer 重试；"
            "正文必须至少让证据、退路、访问/关系、风险/时间窗口或待验证条件中的一项发生具体变化。"
            "仍须阻断真正的硬设定、时间线、地点、角色状态、核心事件冲突，unknown/candidate 不得升级为确认事实。"
        ),
        "extractor": (
            "【V62 阶段突破】只沉淀本章真正带来的信息性结果、现实代价或更具体的待验证条件。"
            "换站位、重复听声、重复等待、重复解释未知不生成新的进展记忆；如果悬念仍未解，记录行动使其收窄到的具体条件，"
            "并保持 candidate/unknown。不得把推测、计划或未发生的突破升级为 accepted。"
        ),
    }
    return v61_state_progression_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v63_chapter_closure_hint(agent_type: str = "writer") -> str:
    """Make each chapter resolve one bounded objective instead of only relocating discovery."""
    if not prompt_version_at_least("V63"):
        return ""
    guidance = {
        "planner": (
            "【V63 章节闭环】沿用 V62 的阶段突破，但本章必须先确定一个可在本章结尾判定的局部目标，"
            "并在 outline 中明确 goal、阻力、选择、结果和下一步边界。结果可以是成功、失败、付出代价或得到可验证的否定，"
            "但不能只是到达新地点、发现新未知或把问题继续往后推。目标必须服务于主线，并来自上一章状态、角色目标、已有事实或本章可见压力。"
            "一次核心行动只能服务这个目标；若答案不能揭示，必须让行动至少排除一个具体可能、关闭一条现实退路，或证明一个明确条件未满足。"
            "不得为了闭环新增人物、物品、地点、身份、能力、机制、授权或因果。"
        ),
        "writer": (
            "【V63 章节闭环】把本章写成一个能落地的局部目标，而不是通往下一章的探索走廊。"
            "先让目标和阻力进入现场，再让角色做一次带取舍的行动；行动必须产生可观察回应，随后在本章内给出可判定结果："
            "成功、失败、现实代价，或一个被行动明确排除/收窄的条件都可以。仅进入新地点、看见新未知、听见新声响、继续等待或把疑问改写一遍都不算结果。"
            "结尾要让读者知道本章完成了什么、失去了什么，或哪一个具体条件已经被证明不成立；下一章可以继续悬念，但不能用新未知替代本章结果。"
            "只使用已有事实和章节契约，不新增人物、物品、地点、身份、能力、机制、授权或因果。"
        ),
        "editor": (
            "【V63 章节闭环】检查正文是否围绕一个可判定的局部目标完成了目标、阻力、选择和结果。"
            "压缩只负责换地点、发现未知、重复听声或继续等待的过渡段；优先保留正文已有的成功、失败、代价、排除条件和退路关闭。"
            "如果本章只留下新地点或新问题，在不新增事实的前提下把已有回应和代价组织成明确结果；这是局部叙事修复，不单独触发 Writer 重写。"
            "不得新增事件、实体、机制、授权或答案；只有硬事实、时间线、地点、角色状态、核心事件或严重断章问题才允许 rewrite。"
        ),
        "validator": (
            "【V63 章节闭环】除 V62 的信息性结果/真实代价检查外，核对本章是否有一个可定位的局部目标，以及正文是否给出可判定结果。"
            "成功、失败、代价或被行动明确排除的具体条件都算结果；只有新地点、新未知、新声响、等待或重复提问不算。"
            "缺少闭环属于 narrative warning，不单独触发 Writer 重试；若同时缺少章节核心事件或违反 accepted/published/user/frozen 事实、时间线、地点、角色状态，才按硬问题阻断。"
            "unknown/candidate 仍不得升级为身份、历史、因果、授权或机制事实。"
        ),
        "extractor": (
            "【V63 章节闭环】优先沉淀本章局部目标的实际结果、失败原因、现实代价或被行动排除的具体条件，"
            "再记录由此产生的新阶段。只到达新地点、发现未知、重复听声、等待或改写疑问不生成独立进展记忆。"
            "结果来源不明、因果未证实或只是计划的内容保持 candidate/generated/unknown，不升级为 accepted。"
        ),
    }
    return v62_stage_breakthrough_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v64_cross_chapter_stage_transition_hint(agent_type: str = "writer") -> str:
    """Make the previous terminal state a handoff boundary, not a new action.

    V63 improved local chapter closure but still allowed a serial investigation
    to replay the previous chapter's final action as the next chapter's setup.
    V64 keeps the existing schema and turns the handoff into an explicit
    three-part execution rule: inherited result, forbidden replay, new stage.
    """
    if not prompt_version_at_least("V64"):
        return ""
    guidance = {
        "planner": (
            "【V64 跨章阶段切换】把交接包中的 completed_event_ledger、previous_terminal_state 和 inherited_state 当作上一章已经成立的事实，"
            "先在规划中排除已完成动作，再确定本章唯一的新 stage_entry。new_stage_delta 必须同时说明：上一章已完成的终态、"
            "本章不再重复的动作、以及本章由角色选择真正打开的新入口/新位置/新风险/新关系/新调查条件。"
            "required_events、primary_action 和 character_turn 只能服务这个新入口；不得把‘离开原处、设备保持不变、等待无效、再次确认未知’"
            "写成新的核心动作。若上一章已经完成了某个观察或退出，本章第一核心动作必须发生在其后的不同阶段，并让至少一个可观察状态改变。"
            "不得新增人物、物品、地点、身份、能力、机制、授权或因果。"
        ),
        "writer": (
            "【V64 跨章阶段切换】上一章的 completed_event_ledger、previous_terminal_state 和 inherited_state 不是本章待执行的任务，"
            "而是已经结束的开场条件。只用一句结果性承接说明角色现在处于什么状态，然后立即进入 new_stage_delta 的新入口。"
            "禁止把上一章已经完成的离开、退开、关闭、等待、设备未变化、重复读取或‘仍未知’重新写成当前章的动作、阻力或高潮。"
            "本章第一段之后必须出现与上一章不同的角色选择，并在现场产生新的位置、可用渠道、风险、关系距离、调查条件或现实代价；"
            "如果暂时不能揭示答案，就改变问题的范围或代价，而不是重复原问题。结尾落在这个新阶段的结果，不回到上一章终态。"
            "只使用已有事实和章节契约，不新增人物、物品、地点、身份、能力、机制、授权或因果。"
        ),
        "editor": (
            "【V64 跨章阶段切换】逐项对照上一章 completed_event_ledger/previous_terminal_state 与本章 new_stage_delta。"
            "把上一章已完成的离开、关闭、等待、设备不变、重复确认和未知复述压缩为一句承接，不能让它们继续占据本章的动作位。"
            "优先把正文已有的新入口、角色选择、位置/风险/渠道/关系/调查条件变化前置并连成结果；不得凭空制造新阶段。"
            "若本章只有复演而没有任何可观察的新阶段，记录为 narrative warning；只有硬事实、时间线、地点、角色状态、核心事件或严重断章冲突才允许 Writer 重写。"
        ),
        "validator": (
            "【V64 跨章阶段切换】把上一章终态视为本章起始边界，核对本章是否真正离开该边界。"
            "检查三件事：已完成动作没有被重新执行；本章第一核心动作属于 new_stage_delta；结尾至少有一个与上一章不同的可观察状态或现实代价。"
            "‘再次离开/再次退开/设备仍不变/等待无效/继续确认未知’只能算重复或 narrative warning，不能单独触发 Writer 重试。"
            "若正文与章节契约、accepted/published/user/frozen 事实、时间线、地点、角色状态或核心事件冲突，仍按硬问题阻断；unknown/candidate 不得升级为确认事实。"
        ),
        "extractor": (
            "【V64 跨章阶段切换】不要把上一章 completed_event_ledger 或 previous_terminal_state 的继承状态再次沉淀为新进展。"
            "只提取本章相对上一章新增的入口、位置、风险、关系、渠道、调查条件、角色选择和现实代价；重复离开、等待、设备未变化或未知复述标为 inherited/replayed。"
            "若新阶段的原因、归属或因果没有正文证据，保持 candidate/generated/unknown，不升级为 accepted。"
        ),
    }
    return v63_chapter_closure_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v65_evidence_boundary_hint(agent_type: str = "writer") -> str:
    """Keep observed surfaces from becoming confirmed object states."""
    if not prompt_version_at_least("V65"):
        return ""
    guidance = {
        "planner": (
            "【V65 证据边界闸门】为每个关键推进同时写清‘正文可直接观察到的内容’和‘仍不能确认的解释’，"
            "沿用现有 primary_action、character_turn、new_stage 和 end_state 字段，不新增字段。"
            "屏幕文字只能规划为屏幕显示，脚印、拖痕和残片只能规划为现场痕迹；不得把它们直接规划成真实转移、物品身份、执行者、归属、来源或因果。"
            "如果本章需要推进未知，只推进调查入口、核查条件或代价，不提前兑现未知答案。"
        ),
        "writer": (
            "【V65 证据边界闸门】所有涉及设备显示、回执、脚印、拖痕、刻痕、残片或角色判断的段落，必须按‘可见观察 -> 有限推断 -> 尚待核查’落地。"
            "设备显示是界面事件，不等于目标真实存在、已经转移、确切位置或设备机制；脚印/拖痕是痕迹，不等于确认执行者、携带者、物品性质、归属或交付因果。"
            "禁止用‘证明了、确认是、已经被带走、对象确实、就是、因此可知’把来源不足的线索收束成事实；改用‘显示为、痕迹指向、可能、尚不能确认、需要核查’。"
            "结尾可以留下新追读问题，但必须把问题写成待核查线索，不得先把线索答案写死。不得新增人物、物品、地点、身份、能力、机制、授权或因果。"
        ),
        "editor": (
            "【V65 证据边界闸门】优先扫描正文中把界面显示/现场痕迹/角色推断写成真实对象状态、执行者、物品性质、归属或因果的句子。"
            "只替换越界句为‘观察到的表面 + 有限推断 + 尚待核查’，保留原有动作、人物选择、阶段推进和结尾悬念；不得新增答案或改变章节事件。"
            "单纯证据语气越界属于局部修复，不要求 Writer 重写整章；只有实际违反已接受事实、时间线、地点、角色状态、物品状态或核心事件时才阻断。"
        ),
        "validator": (
            "【V65 证据边界闸门】区分两类问题：如果正文只是把设备显示、痕迹或角色猜测说得过于确定，但没有改变已接受事实、实际物品状态、人物状态、地点、时间线或核心事件，标为 evidence_boundary/local_repair，提供原句和安全替换，不单独触发 Writer 重试。"
            "只有越界表达进一步推动了未经证实的硬动作，或与 accepted/published/user/frozen 事实、时间线、地点、角色状态、物品状态、核心事件明确冲突，才输出 block。"
            "设备显示不得单独证明目标存在或真实转移；痕迹不得单独证明执行者、携带者、物品性质、归属或因果。"
        ),
        "extractor": (
            "【V65 证据边界闸门】从正文分开沉淀 observation 和 interpretation：设备显示、回执、脚印、拖痕、刻痕、残片只记录为已观察表面或 candidate/generated 线索；"
            "只有正文明确发生且有直接动作证据的状态变化才能作为当前变化。不得从显示文字推断真实转移，从痕迹推断执行者/物品性质，或把角色猜测升级为 accepted。"
        ),
    }
    return v64_cross_chapter_stage_transition_hint(agent_type) + "\n\n" + guidance.get(agent_type, guidance["writer"])


def v66_compact_character_texture_hint(agent_type: str = "writer") -> str:
    """Keep the generation surface narrative-first while retaining hard boundaries.

    V65 proved that evidence language can be repaired locally, but its long
    chained hint surface still encouraged repeated explanations. V66 is an
    experiment-only compact replacement for the generation hint; backend
    validation and V65 local-repair policy remain active through the version
    gate.
    """
    if not prompt_version_at_least("V66"):
        return ""
    guidance = {
        "planner": (
            "【V66 单章叙事执行面】本章只规划一个可判定目标：目标、现场压力、角色选择、可见回应、承担的代价和结尾状态。"
            "角色选择必须来自角色卡/上一章已发生状态或本章可见压力，并体现一个具体行为倾向；不要新增性格、背景、关系或能力。"
            "证据只写观察表面和待核查边界，不把界面、痕迹或猜测规划成身份、来源、真实物品状态或因果。"
            "只保留一次必要的证据边界说明，后续用动作、位置、时间成本、风险或关系距离推进，不用解释性节拍填充大纲。"
        ),
        "writer": (
            "【V66 单章叙事执行面】把本章写成一条完整现场链：已有压力 -> 角色具体选择 -> 一次动作 -> 可见回应 -> 人物承担的代价/风险 -> 新的结尾状态。"
            "让角色的既有状态通过一个可见的身体反应、操作习惯、停顿方式、取舍或拒绝显出来；不要直接解释‘他很谨慎/焦虑/执着’，也不要新增性格和背景。"
            "同一个限制、未知或结论只解释一次；之后让动作和现场变化承担叙事。禁止用再次观察、重复确认、心理总结或换一种说法复述同一信息。"
            "设备显示、回执、脚印、拖痕和猜测只写成可见观察、有限推断和待核查线索；不得升级为真实存在、执行者、归属、转移、来源或因果。"
            "只使用已有事实与章节契约，不新增人物、物品、地点、身份、能力、机制、授权或未经证实的结果。"
        ),
        "editor": (
            "【V66 叙事密度局部修复】优先删并合并重复解释：同一限制/未知/结论只保留一次；把正文已有的角色动作、停顿、取舍、位置变化和现实代价前置。"
            "保留一个清晰的‘压力 -> 选择 -> 回应 -> 代价 -> 终态’链条，不为增加人物纹理新增事实。"
            "界面或痕迹越界只改为观察/有限推断/待核查；与 accepted、published、user、frozen 事实、时间线、地点、物品状态、角色状态或核心事件冲突仍是硬问题。"
        ),
        "validator": (
            "【V66 叙事质量边界】将重复解释、人物纹理不足和缺少即时余压列为 writing_quality/character_portrayal warning，不单独触发 Writer 重写。"
            "检查正文是否有一个可定位的角色选择及其可见代价；没有只能报告质量建议。"
            "仍须阻断 accepted/published/user/frozen 事实、时间线、地点、物品状态、角色状态和核心事件冲突；界面、痕迹或猜测未改变硬状态时按 V65 evidence_boundary/local_repair 处理。"
        ),
        "extractor": (
            "【V66 记忆沉淀边界】只沉淀本章正文明确发生的角色选择、动作、回应、代价和新终态；重复解释不生成新记忆。"
            "设备显示与现场痕迹只作为 observation 或 candidate/unknown 线索保存，未经直接正文证据不得升级为 accepted 的身份、来源、归属、转移或因果。"
        ),
    }
    return guidance.get(agent_type, guidance["writer"])


# ---------------------------------------------------------------------------
# 表面注册
# ---------------------------------------------------------------------------
# 生产侧的 generation_hints 只内联 A28/V43 栈；V44+ 各自**整体替换**该栈，
# 因此这里按版本从高到低选出唯一胜出者。
_GENERATION_HINT_CHAIN = (
    ("V54", v54_intra_chapter_action_repair_hint),
    ("V53", v53_cross_chapter_stage_hint),
    ("V52", v52_visible_consequence_chain_hint),
    ("V51", v51_character_agency_hint),
    ("V50", v50_minimal_observation_patch_hint),
    ("V49", v49_observation_language_hint),
    ("V47", v47_narrative_realization_hint),
    ("V46", v46_dramatic_turn_hint),
    ("V45", v45_narrative_delta_hint),
    ("V44", v44_compact_input_surface_hint),
)


# ---------------------------------------------------------------------------
# 生产 hint 的带门包装
# ---------------------------------------------------------------------------
# 原代码里 V34+ 分支是一个**固定调用列表**，每个 hint 用自己的门自我过滤：
# 在 prompt_version=V34 时，v36–v43 各自返回空串，实际表面只有 v34+v32。
#
# 生产冻结在 V43，那些门恒为真，因此已从 `agents/prompt_hints.py` 移除。研究
# 路径要复现 V34–V42 就必须把门加回来——这就是下面这组包装存在的原因。

def _gated(version: str, func):
    """把无门的生产 hint 包装成"低于 version 时返回空串"。"""

    def wrapper(agent_type: str) -> str:
        return func(agent_type) if prompt_version_at_least(version) else ""

    wrapper.__name__ = f"{func.__name__}_gated"
    wrapper.__doc__ = f"{func.__name__}，在低于 {version} 时返回空串。"
    return wrapper


v7_continuity_state_hint_gated = _gated("V7", v7_continuity_state_hint)
v32_prompt_surface_hint_gated = _gated("V32", v32_prompt_surface_hint)
v33_memory_update_protocol_hint_gated = _gated("V33", v33_memory_update_protocol_hint)
v34_context_ownership_hint_gated = _gated("V34", v34_context_ownership_hint)
v35_writer_narrative_hint_gated = _gated("V35", v35_writer_narrative_hint)
v36_artifact_commitment_hint_gated = _gated("V36", v36_artifact_commitment_hint)
v37_observation_interpretation_hint_gated = _gated("V37", v37_observation_interpretation_hint)
v38_scene_motion_hint_gated = _gated("V38", v38_scene_motion_hint)
v39_single_evidence_delta_hint_gated = _gated("V39", v39_single_evidence_delta_hint)
v40_contract_state_hint_gated = _gated("V40", v40_contract_state_hint)
v41_narrative_escalation_hint_gated = _gated("V41", v41_narrative_escalation_hint)
v42_authority_locked_progression_hint_gated = _gated("V42", v42_authority_locked_progression_hint)
v43_bounded_hypothesis_progression_hint_gated = _gated("V43", v43_bounded_hypothesis_progression_hint)


@register("generation_hints")
def generation_hints(agent_type: str):
    """V44+ 的 generation_hints 覆盖。低于 V44 时交给 `_pre_v44_generation_hints`。"""
    for version, func in _GENERATION_HINT_CHAIN:
        if prompt_version_at_least(version):
            return func(agent_type)
    return _pre_v44_generation_hints(agent_type)


# ---------------------------------------------------------------------------
# V0–V43 的逐 agent 链
# ---------------------------------------------------------------------------
# 生产只内联 A28/V43 胜出的那一条分支；V34 以下的分支同样是"死代码"，因此一并
# 移到这里。各 agent 的链**不相同**，这是从各 agent 源码逐条抄录的，不要合并。

def _v27_common(agent_type: str) -> str:
    return (
        v7_continuity_state_hint_gated(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
        + v27_narrative_first_hint(agent_type)
        + v28_action_ownership_hint(agent_type)
    )


def _planner_pre_v44(agent_type: str) -> str:
    if prompt_version_at_least("V34"):
        return (
            v43_bounded_hypothesis_progression_hint_gated(agent_type)
            + v42_authority_locked_progression_hint_gated(agent_type)
            + v41_narrative_escalation_hint_gated(agent_type)
            + v40_contract_state_hint_gated(agent_type)
            + v39_single_evidence_delta_hint_gated(agent_type)
            + v38_scene_motion_hint_gated(agent_type)
            + v37_observation_interpretation_hint_gated(agent_type)
            + v36_artifact_commitment_hint_gated(agent_type)
            + v34_context_ownership_hint_gated(agent_type)
            + v32_prompt_surface_hint_gated(agent_type)
        )
    if prompt_version_at_least("V32"):
        return v32_prompt_surface_hint_gated(agent_type)
    if prompt_version_at_least("V29"):
        return (
            v29_compact_narrative_hint(agent_type)
            + v31_evidence_ordered_continuity_hint(agent_type)
        )
    if prompt_version_at_least("V27"):
        return _v27_common(agent_type)
    return (
        v7_continuity_state_hint_gated(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v12_evidence_surface_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
        + v13_narrative_density_hint(agent_type)
        + v14_continuity_language_hint(agent_type)
        + v15_compact_evidence_and_character_action_hint(agent_type)
    )


def _writer_pre_v44(agent_type: str) -> str:
    if prompt_version_at_least("V35"):
        return (
            v43_bounded_hypothesis_progression_hint_gated(agent_type)
            + v42_authority_locked_progression_hint_gated(agent_type)
            + v41_narrative_escalation_hint_gated(agent_type)
            + v40_contract_state_hint_gated(agent_type)
            + v39_single_evidence_delta_hint_gated(agent_type)
            + v38_scene_motion_hint_gated(agent_type)
            + v37_observation_interpretation_hint_gated(agent_type)
            + v36_artifact_commitment_hint_gated(agent_type)
            + v35_writer_narrative_hint_gated(agent_type)
        )
    if prompt_version_at_least("V34"):
        return v34_context_ownership_hint_gated(agent_type) + v32_prompt_surface_hint_gated(agent_type)
    if prompt_version_at_least("V32"):
        return v32_prompt_surface_hint_gated(agent_type)
    if prompt_version_at_least("V29"):
        return (
            v29_compact_narrative_hint(agent_type)
            + v31_evidence_ordered_continuity_hint(agent_type)
        )
    if prompt_version_at_least("V27"):
        return _v27_common(agent_type)
    return (
        v6_continuity_quality_hint(agent_type)
        + v7_continuity_state_hint_gated(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v12_evidence_surface_hint(agent_type)
        + v13_narrative_density_hint(agent_type)
        + v14_continuity_language_hint(agent_type)
        + v15_compact_evidence_and_character_action_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
    )


def _v34_stack_with_tail(agent_type: str, *tail) -> str:
    return (
        v43_bounded_hypothesis_progression_hint_gated(agent_type)
        + v42_authority_locked_progression_hint_gated(agent_type)
        + v41_narrative_escalation_hint_gated(agent_type)
        + v40_contract_state_hint_gated(agent_type)
        + v39_single_evidence_delta_hint_gated(agent_type)
        + v38_scene_motion_hint_gated(agent_type)
        + v37_observation_interpretation_hint_gated(agent_type)
        + v36_artifact_commitment_hint_gated(agent_type)
        + "".join(hint(agent_type) for hint in tail)
    )


def _editor_pre_v44(agent_type: str) -> str:
    if prompt_version_at_least("V34"):
        return _v34_stack_with_tail(
            agent_type, v34_context_ownership_hint_gated, v32_prompt_surface_hint_gated
        )
    if prompt_version_at_least("V32"):
        return v32_prompt_surface_hint_gated(agent_type)
    return (
        v6_continuity_quality_hint(agent_type)
        + v7_continuity_state_hint_gated(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v12_evidence_surface_hint(agent_type)
        + v13_narrative_density_hint(agent_type)
        + v14_continuity_language_hint(agent_type)
        + v15_compact_evidence_and_character_action_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
        + v27_narrative_first_hint(agent_type)
        + v28_action_ownership_hint(agent_type)
        + v31_evidence_ordered_continuity_hint(agent_type)
    )


def _validator_pre_v44(agent_type: str) -> str:
    if prompt_version_at_least("V34"):
        return _v34_stack_with_tail(
            agent_type, v34_context_ownership_hint_gated, v32_prompt_surface_hint_gated
        )
    if prompt_version_at_least("V32"):
        return v32_prompt_surface_hint_gated(agent_type)
    # 注意：validator 的这条分支没有 v7（它在 sys_prompt 末尾被单独追加）。
    return (
        v6_continuity_quality_hint(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v12_evidence_surface_hint(agent_type)
        + v13_narrative_density_hint(agent_type)
        + v14_continuity_language_hint(agent_type)
        + v15_compact_evidence_and_character_action_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
        + v27_narrative_first_hint(agent_type)
        + v28_action_ownership_hint(agent_type)
        + v31_evidence_ordered_continuity_hint(agent_type)
    )


def _extractor_pre_v44(agent_type: str) -> str:
    if prompt_version_at_least("V34"):
        return _v34_stack_with_tail(
            agent_type,
            v34_context_ownership_hint_gated,
            v33_memory_update_protocol_hint_gated,
            v32_prompt_surface_hint_gated,
        )
    if prompt_version_at_least("V33"):
        return (
            v33_memory_update_protocol_hint_gated(agent_type)
            + v32_prompt_surface_hint_gated(agent_type)
        )
    if prompt_version_at_least("V32"):
        return v32_prompt_surface_hint_gated(agent_type)
    return (
        v7_continuity_state_hint_gated(agent_type)
        + v8_evidence_state_hint(agent_type)
        + v9_temporal_evidence_hint(agent_type)
        + v10_context_compaction_hint(agent_type)
        + v11_continuity_boundary_hint(agent_type)
        + v12_evidence_surface_hint(agent_type)
        + v13_narrative_density_hint(agent_type)
        + v14_continuity_language_hint(agent_type)
        + v15_compact_evidence_and_character_action_hint(agent_type)
        + v20_low_retry_state_hint(agent_type)
        + v21_numeric_and_cache_boundary_hint(agent_type)
        + v22_single_countdown_hint(agent_type)
        + v23_temporal_anchor_hint(agent_type)
        + v24_inherited_state_hint(agent_type)
        + v25_artifact_boundary_hint(agent_type)
        + v27_narrative_first_hint(agent_type)
        + v28_action_ownership_hint(agent_type)
        + v31_evidence_ordered_continuity_hint(agent_type)
    )


_PRE_V44_BY_AGENT = {
    "planner": _planner_pre_v44,
    "writer": _writer_pre_v44,
    "editor": _editor_pre_v44,
    "validator": _validator_pre_v44,
    "extractor": _extractor_pre_v44,
}


def _pre_v44_generation_hints(agent_type: str) -> str:
    builder = _PRE_V44_BY_AGENT.get(agent_type, _writer_pre_v44)
    return builder(agent_type)


# ---------------------------------------------------------------------------
# 其余表面的研究覆盖
# ---------------------------------------------------------------------------


@register("chapter_contract_output_requirements")
def chapter_contract_output_requirements():
    """Planner 章节契约输出要求的 V0–V53 变体。"""
    if prompt_version_at_least("V34"):
        text = (
            "\n\n【V34 章节契约输出要求】\n"
            "输出 required_events、uncertain_events、continuity_from_previous、state_changes、"
            "foreshadowing_actions、forbidden_deviations、unknown_boundary 和 continuity_contract。"
            "continuity_from_previous 只记录上一章继承状态；required_events 和 state_changes 只记录本章新增动作与可见后果。"
            "不得把继承状态重复包装成新的剧情事件。"
        )
        if prompt_version_at_least("V53"):
            text += (
                "\n\n【V53 跨章阶段输出要求】输出非空 new_stage_delta，明确相对上一章 completed_event_ledger 和终态的新增阶段、"
                "新入口、关系、位置、风险或策略变化；不得把上一章已完成动作再次列为 required_events。"
            )
        return text
    if prompt_version_at_least("V32"):
        return (
            "\n\n【V32 章节契约输出要求】\n"
            "输出 required_events、uncertain_events、continuity_from_previous、state_changes、"
            "foreshadowing_actions、forbidden_deviations、unknown_boundary 和 continuity_contract。"
            "先列已继承的可观察状态，再列本章角色动作和可见后果；未知关系只能留在 uncertain_events，"
            "不得写成因果、先后、来源、身份或控制结论。"
        )
    if prompt_version_at_least("V29"):
        text = (
            "\n\n【V29 章节契约输出要求】\n"
            "输出 required_events、uncertain_events、continuity_from_previous、state_changes、"
            "foreshadowing_actions、forbidden_deviations、unknown_boundary 和 continuity_contract。"
            "required_events 只写推动场景的可验证动作或选择；不要把后台字段、证据术语或审计规则写进正文计划。"
        )
        if prompt_version_at_least("V31"):
            text += (
                "\n\n【V31 执行顺序输出要求】\n"
                "continuity_from_previous 只写上一章已经观察到的继承状态；required_events 只写本章角色动作、选择或核验；"
                "uncertain_events 保留未校准的关系；forbidden_deviations 明确禁止把观察升级成实际先后、因果、来源、身份或控制。"
            )
        return text

    text = ""
    if prompt_version_at_least("V2"):
        text = (
            "\n\n【章节契约输出要求】\n"
            "除既有字段外，必须输出 required_events、uncertain_events、"
            "continuity_from_previous、state_changes、foreshadowing_actions、"
            "forbidden_deviations、unknown_boundary 和 continuity_contract。"
            "required_events 只写本章必须执行的可验证动作或场面；契约必须具体到本章可验证的事件和状态。"
        )
    if prompt_version_at_least("V3"):
        text += (
            "\n\n【V3 权威边界要求】\n"
            "章节契约只能把有明确来源的事实写成确认内容。对声音、身份、地点、物品归属、"
            "生死和因果等仍未确认的信息，required_events 只能写调查、观察、追问或推进动作，"
            "不得写成已经揭示的结论。若 key_events 与 unknown_boundary 冲突，保留 unknown，"
            "把该项放入 uncertain_events，并在 forbidden_deviations 中写明不得越过的边界。"
        )
    if prompt_version_at_least("V27"):
        text += (
            "\n\n【V27 叙事优先契约】\n"
            "仍须输出结构化契约，但 required_events 只保留推动场景的可验证动作；"
            "不要为了填充契约新增证据字段、设备回执、记录页、读取者标记或审计清单。"
            "只有交接包中已经存在的证据账本或本章大纲明确要求的可见证据，才可规划对应核对动作。"
        )
    if prompt_version_at_least("V28"):
        text += (
            "\n\n【V28 动作归属契约】\n"
            "界面读取、展开或确认只能改变可见信息，不能直接改变实体状态；"
            "需要进入、移动或产生实体变化时，必须明确角色的物理动作，或把机制保留为未知观察。"
        )
    return text


@register("writer_context_policy")
def writer_context_policy():
    """V35 以下 Writer 仍直接收交接包、章节契约和上一章结尾。"""
    v35 = prompt_version_at_least("V35")
    return {
        "suppress_handoff_and_contract": v35,
        "suppress_previous_ending": v35,
    }


@register("writer_rewrite_requirements")
def writer_rewrite_requirements():
    """V5 以下没有定点重写要求。"""
    if not prompt_version_at_least("V5"):
        return ""
    return (
        "\n\n【V5 定点重写要求】\n"
        "若收到上一轮校验或编辑错误，逐条处理其中的正文证据、冲突事实和修复建议；"
        "只修改被证据定位的问题，保留章节契约、上一章交接和已确认事实。"
        "禁止使用“重新写得更好”这类泛化目标，也不得借重写补全 unknown 或 candidate/generated 线索。"
    )


_REPAIR_CHAIN = (
    ("V54", v54_intra_chapter_action_repair_hint),
    ("V53", v53_cross_chapter_stage_hint),
    ("V52", v52_visible_consequence_chain_hint),
    ("V51", v51_character_agency_hint),
    ("V50", v50_minimal_observation_patch_hint),
)


@register("repair_surface_hints")
def repair_surface_hints(agent_type: str):
    """Editor 强制修订 / Extractor 辅助路径的 V50+ 额外 hint。"""
    for version, func in _REPAIR_CHAIN:
        if prompt_version_at_least(version):
            return func(agent_type)
    return ""


@register("editor_policy")
def editor_policy():
    """Editor 审阅策略与结构开关的历史版本取值。"""
    if prompt_version_at_least("V5"):
        review_strategy = (
            "\n\n【低重试审阅策略】\n"
            "只有硬性设定/时间线冲突、核心事件缺失、严重断章或无法局部修复的结构问题才允许 decision= rewrite。"
            "文风、轻微节奏和局部措辞问题必须直接在 edited_content 中修复。"
            "除原有五维评分外，evaluations 增加 chapter_continuity 和 foreshadowing_payoff 两项，均为 1-10 分并引用具体依据。"
        )
    elif prompt_version_at_least("V1"):
        review_strategy = (
            "\n\n【连续性研究评分要求】\n"
            "除原有五维评分外，evaluations 必须增加 chapter_continuity 和 "
            "foreshadowing_payoff 两项，均为 1-10 分。每项 reason 必须引用本章正文、"
            "上一章交接包、章节大纲或伏笔账本中的具体证据；证据不足时不得臆测高分。"
        )
    else:
        review_strategy = ""

    return {
        "review_strategy": review_strategy,
        "project_outline": prompt_version_at_least("V44"),
        "long_form_quality_contract": prompt_version_at_least("V19"),
        "research_response_schema": prompt_version_at_least("V1"),
    }
