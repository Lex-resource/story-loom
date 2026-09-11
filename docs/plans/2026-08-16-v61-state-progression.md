# V61 状态演进收束

## Goal

V60 已经能促使角色离开设备并改变调查方向，但 A46 第 3 章暴露了两个问题：正文仍重复解释设备边界，Extractor 将同一世界对象的后续状态误判成硬冲突并阻断发布。V61 验证“状态演进”是否能同时降低叙事复述和错误人工复核。

## Controlled change

保留 V60 的结构化角色转折、界面外部后果、四层记忆权威边界、OpenAI-only、关闭 hybrid recall、无额外模型调用和现有重试策略。

新增两项同一变量下的配套约束：

- 五个 Agent 将同一对象的显示、熄灭、关闭、位置或渠道变化写成连续状态演进，设备限制最多解释一次，结尾必须落到新的具体状态。
- 生成型 world rule 的 `rule` 与历史数据中的 `confirmed` 仅视为类型别名；真实能力、地点、权限、时间线、冻结标记变化仍阻断。

## Runtime

从固定第 1 章种子创建新项目和新记忆命名空间，使用 OpenAI / `gpt-5.6-luna`，备用 Provider 和 hybrid recall 关闭，`bootstrap_skeleton=false`，生成第 2-10 章。A46 原始项目和暂停状态不复用、不覆盖。

## Gate

首个 Planner/Writer Prompt 必须包含 V61，且 Planner 输出非空 `primary_action` 与 `character_turn`。每章记录质量七维、内容/API/JSON 重试、模型调用、Token、墙钟、记忆上下文和冲突队列数量。V61 仅在完成十章后与 A45/A46 的有效观察比较，不提前宣布最佳。
