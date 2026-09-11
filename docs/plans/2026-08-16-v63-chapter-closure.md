# V63 章节闭环

## Goal

验证 V62 的“阶段突破”是否仍允许模型用“进入新地点、发现新未知、继续验证”替代本章结果。V63 在不增加模型调用、字段、数据库结构或记忆层的前提下，要求每章围绕一个可在章末判定的局部目标完成一次闭环。

## Controlled change

保留 V62 的信息性结果、真实代价、四层记忆权威边界、OpenAI-only、关闭备用 Provider 与 hybrid recall、低重试策略和现有角色转折结构。

新增仅提示词层的章节闭环约束，覆盖 Planner、Writer、Editor、Validator、Extractor。局部结果可以是成功、失败、现实代价，或被行动明确排除的具体条件；仅换地点、听见新声响、继续等待或改写未知不算结果。Validator 对闭环不足只报 narrative warning，不触发 Writer 重写。

## Runtime

停止或保留未完成的 A48/V62 原始运行，不共享其正文或记忆。使用相同固定第 1 章种子创建全新项目和记忆命名空间，使用 OpenAI / `gpt-5.6-luna`，关闭备用 Provider 与 hybrid recall，生成第 2-10 章。运行 ID 使用 `ariadne-a49-v63-chapter-closure-10ch-20260816`。

## Gate and evaluation

首个 Planner/Writer Prompt 必须包含 V63，且 Planner 输出非空 `primary_action` 与 `character_turn`。每章记录七维质量、内容/API/JSON 重试、LLM 调用、Token、墙钟、记忆上下文和冲突队列。重点比较局部目标闭环、剧情推进、人物塑造、文笔质量、章节衔接和伏笔兑现，并检查章节是否仍以新地点/新未知代替结果。

V63 不因单纯闭环不足触发 Writer 重试，继续保持低重试目标；只有硬事实、时间线、地点、角色状态、核心事件或严重断章才阻断。完成十章后与 A45/V59、A46/V60、A47/V61、A48/V62 的有效观察对比，不提前宣布最佳。
