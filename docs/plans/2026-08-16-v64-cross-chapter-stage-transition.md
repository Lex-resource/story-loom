# V64 跨章阶段切换

## Goal

验证 V63 的章节闭环是否因为没有把“上一章终态”变成明确的开场边界，仍允许连续调查场景重复上一章已经完成的离开、等待、设备未变化和未知复述。

## Controlled change

保留 V63 的章节闭环、V62 阶段突破、V61 状态演进、V58 结构化角色转折、分层记忆权威边界、OpenAI-only、关闭备用 Provider 与 hybrid recall、低重试策略和现有 schema。

只新增提示词层的 V64 跨章阶段切换规则，覆盖 Planner、Writer、Editor、Validator、Extractor。交接包中的 `completed_event_ledger`、`previous_terminal_state` 和 `inherited_state` 被明确视为已经成立的开场条件；本章必须从 `new_stage_delta` 指定的新入口开始，禁止把上一章已完成动作重新占据本章动作位。V64 不新增字段、数据库表、记忆层或模型调用。

## Expected mechanism

Planner 仍使用已有的 `new_stage_delta`、`primary_action` 和 `character_turn`，但必须同时表达上一章终态、本章禁止重做的动作以及真正的新阶段。Writer 只用一句结果性承接，然后直接写新入口和新的角色选择。Editor 只压缩旧终态复演并突出正文已有的新变化；Validator 将复演记为 narrative warning，不因单纯叙事不足触发 Writer 重试；Extractor 只沉淀相对上一章新增的状态。

## Runtime

停止或保留 A49/V63 的原始运行和 artifacts，不共享正文或记忆。使用相同固定第 1 章种子创建全新项目和记忆命名空间，使用 OpenAI / `gpt-5.6-luna`，关闭备用 Provider 与 hybrid recall，生成第 2-10 章。运行 ID 使用 `ariadne-a50-v64-cross-chapter-stage-transition-10ch-20260816`。

## Evaluation

重点观察跨章重复动作、章节衔接、剧情推进、人物塑造、文笔质量、内容重试和伏笔推进。每章继续记录七维质量、LLM 调用与尝试、API/JSON/内容重试、Token、墙钟、记忆上下文和实际 Prompt。V64 只有在十章完成后才参与正式比较。

