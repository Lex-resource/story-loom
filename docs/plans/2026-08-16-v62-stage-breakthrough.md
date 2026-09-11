# V62 阶段突破

## Goal

验证 V61 的连续状态提示是否把章节推进压缩成了“换站位、重复观察、继续等待”。V62 在不增加模型调用和数据结构的前提下，要求每章产生信息性结果、真实代价，或一个因行动而更具体的待验证条件。

## Controlled change

保留 V61 的状态演进、外部后果、四层记忆权威边界、OpenAI-only、关闭备用 Provider 和 hybrid recall、低重试策略及现有角色转折结构。

新增仅提示词层的阶段突破约束，覆盖 Planner、Writer、Editor、Validator、Extractor。不新增字段、数据库表、记忆层、前端展示或模型调用。单纯换站位、重复听声、重复等待和重复复述未知，不再视为阶段推进；悬念仍可保持未知，但必须因本章行动而收窄到新的可验证条件。

## Runtime

停止未完成的 A47/V61 运行但保留其原始 artifacts。使用同一固定第 1 章种子创建全新项目和记忆命名空间，使用 OpenAI / `gpt-5.6-luna`，关闭备用 Provider 与 hybrid recall，生成第 2-10 章。运行 ID 使用 `ariadne-a48-v62-stage-breakthrough-10ch-20260816`。

## Gate and evaluation

首个 Planner/Writer Prompt 必须包含 V62，且 Planner 输出非空 `primary_action` 与 `character_turn`。每章记录七维质量、内容/API/JSON 重试、LLM 调用、Token、墙钟、记忆上下文和冲突队列。重点比较 `plot_progression`、`character_portrayal`、`writing_quality` 与 `foreshadowing_payoff`，并检查正文是否仍出现纯观察循环。

V62 不因单纯叙事不足触发 Writer 重试，继续保持低重试目标；只有硬事实、时间线、地点、角色状态、核心事件或严重断章才阻断。完成十章后与 A45/V59、A46/V60、A47/V61 的有效观察对比，不提前宣布最佳。
