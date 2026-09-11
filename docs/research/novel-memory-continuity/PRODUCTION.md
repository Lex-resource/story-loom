# Production Continuity Decision

## Decision

普通长篇生成默认使用 `A28/V43`。这是当前完成十章实验且最适合上线的版本：七维平均 `8.601`，内容重试 `0`，`100%` 生成章节零内容重试，章节衔接 `9.0`，伏笔兑现 `8.667`，平均记忆上下文约 `6,036` 字符。

V43 保留 V42 的权威事实边界，并允许一个明确标记为“假设/待核实”的解释推动可逆调查；每章只要求一个可观察的行动、选择、代价或风险变化。V44-V66 及 A29 的独立复测记录继续保留在研究目录，但不通过默认版本进入生产。A29 两次复测均因 OpenAI 上游 HTTP 400 中止，不能作为 V43 的第二个完整质量样本。

## Runtime Contract

- 四层记忆仍由 PostgreSQL 的 `MemoryAtom`、`SceneBlock`、`Evidence` 和召回服务提供；生产提示只接收 Agent 专属的紧凑召回。
- 交接包和章节契约继续由确定性代码生成，不增加交接专用模型调用。
- `published/user/frozen/accepted` 才能直接作为事实；`candidate/generated` 只能作为待核对线索；`unknown` 禁止补全。
- Validator 只因硬事实、时间线、物品状态、核心事件或章节承接冲突触发 Writer 重写；局部证据措辞和文风问题由 Editor 修复。
- Provider 由 PostgreSQL `SystemSettings.active_provider_id` 决定。上线前应确认 active provider 为 `OpenAI`，备用 provider 为空，embedding 没有模型时明确使用 `chroma_local`。

## Reliability Fixes

同一 Job 内 Validator 触发的 Writer 重试现在共享一个实验上下文，只写一个本章完成事件；暂停后恢复的新 Job 仍作为独立段落，由发布阶段幂等合并。这样不会改变正文或重试决策，只修正墙钟、Token、重试和完成事件的审计口径。

用户暂停和外部终止现在分别记录为 `paused`、`aborted`，只有未处理异常才记录为 `error`，避免暂停操作污染失败率和重试统计。

## Release Checklist

1. 设置 `NOVEL_CONTINUITY_PROMPT_VERSION=V43`，或使用代码默认值。
2. 在系统设置中确认 `OpenAI` 为 active provider，备用 provider 关闭。
3. 确认四层记忆开关和 `NOVEL_MEMORY_CONTEXT_MODE=layered` 开启。
4. 运行定向测试、完整测试、`compileall`、CodeGraph 同步和 backend `/health`。
5. 首次上线生成一章，检查 Planner、Writer、Editor、Validator、Extractor 使用同一 provider，并确认章节只产生一个最终完成事件。

所有研究版本、失败样本、Prompt 快照和原始事件保存在本地分支，不修改压缩包，不推送远端。
