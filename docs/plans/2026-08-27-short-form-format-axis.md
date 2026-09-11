# 短篇格式轴收口计划

> 2026-08-27。前置：2026-08-25 的工作流引擎重构（无计划文档，记录在 CLAUDE.md 的「工作流引擎」一节与硬约束第 8 条）。
> 更早的前置：`2026-07-14-long-short-writing-model.md`，其 Task 1–4 已全部落地。

## 问题

格式轴（`services/workflow_surface.py`）是逐项接的，接了一半就停了。一行代码就是全貌 ——
`agents/writing/validator_agent.py:71`：

```python
sys_prompt = system_tmpl + authority_boundary_hint() + generation_hints + CHARACTER_FACT_SOURCE_RULES + validator_extra_requirements(novel_format) + UNTRUSTED_CONTENT_SYSTEM_REMINDER
```

五个拼接项里 `generation_hints` 与 `validator_extra_requirements(novel_format)` 走格式轴，
`authority_boundary_hint()` 与 `CHARACTER_FACT_SOURCE_RULES` 不走。

由此产生三类实际故障：

**一、短篇 Validator 的判定语言和执行语言是两套。** 短篇模板要求 LLM 用
`logic|consistency|pacing|payoff|viewpoint`（`prompts/validation/zhihu_short_validation.json:8`），
短篇表面宣布只有四类构成 block（`services/short_form_surfaces.py:59-66`）。但
`requires_content_retry()`（`worker_support/generation_validator_policy.py:230-285`）只认
`FACT_CONFLICT_CATEGORIES`（`services/validation_constants.py:12-17`）和
`_V5_RETRYABLE_CATEGORIES`（`:99-110`）两套长篇词表：

| category | 短篇意图 | 现状 |
|---|---|---|
| `consistency` | block | 正常重写 |
| `logic` | block | 正常重写 |
| `viewpoint` | block（人称越权） | **不认 → `force_save_validator_result`，缺陷正文照存并被标 `passed=True`** |
| `payoff` | block（承诺被违背） | **同上** |
| `pacing` | 一律 warning | block 时进 `errors` 再 force_save；长篇同一 issue 是干净的 observe-only |

短篇最致命的两种坏走了最宽容的一条路，而它明确不想阻断的那类反而比长篇更严。

**二、硬约束第 8 条没有机器守着。** `tests/architecture/test_service_boundaries.py` 的五个检查项
没有一个管 `novel_format`。后端残留 6 处硬比，最贵的是 `agents/writing/editor.py:51`：克隆自长篇的
工作流拿到五维提示词配七维 schema，每章必触发校验重试 —— 而同一文件 `:69-71` 的注释把这个失效模式
描述得一清二楚，作者修了 `_response_schema`，漏了上面 20 行的 `_apply_long_form_quality_contract`。

**三、交接包与章节契约五家全量注入。** `planner.py:168-169`、`writer.py:143-144`、
`editor.py:117-118`、`validator_agent.py:50-51`、`extractor.py:68-69`。只有 Writer 那份被清掉了。

## 已定的取舍

**`viewpoint` / `payoff` 都退回 Writer 重写，不引入「退给 Editor 局部修复」的第三档。**
现在只有二档：`requires_content_retry` 为真退回 Writer，为假 `force_save`。第三档要动
`worker_support/generation_validation_flow.py` 的编排，会碰 20 条 golden trace；而短篇只 3 节、
`max_rewrites_override=2`，重写成本本来就低，不值得为此动编排。

**`pacing` 的 observe-only 行为与长篇保持一致**，包括 `quality_gate_override`
（`writing_quality` + 阻断级仍可掉进 errors）。不给短篇额外的宽容度 —— 那是另一个决策，
不在这次范围内。

**不给 `build_chapter_contract` 加格式轴。** 它的签名
（`services/continuity_contract.py:857`，`(outline, handoff, *, enforce_authority)`）没有格式参数，
整个文件零格式轴；`short_form_surfaces.py:229-232` 的注释里作者早已写下「`build_chapter_contract`
是长篇形状的」并选择在简报侧补字段绕过。Task 3 做完后，它的长篇形状产物在短篇路径上就没有消费者了：
原始副本五家全清，唯一剩下的简报通路已被 `execution_brief_boilerplate` 裁掉 4 块兜底
（实测 1490 字符里的 1044 字符）。改它的签名会碰 V43 黄金快照锁定的「契约规范化结果」，代价不划算。

**前端不在这次范围内。** `OutlineSkeletonVisual.jsx:10` 的双判定、`SystemConfigs.jsx` 选不了
`surface_strategy`、`SystemConfigs.jsx:346` 的 `slice(5)`（应为 `slice(0,5)`，导致质量维度提示恒空）、
`streamingJsonParser.js:185` 的长篇硬比 —— 前端零测试覆盖，改动风险最高，单独一期。
唯一例外见 Task 2 步骤 6。

## 不变量

- **长篇字节不变。** 新表面一律走 `workflow_override`，`frozen_v43` 让路。
  `tests/test_v43_production_surface_snapshot.py` 必须零变化，不得用 `V43_SNAPSHOT_UPDATE=1` 重生成。
- **golden trace 不变。** `tests/worker_support/test_generation_trace.py` 的 20 条序列。
  对不上就回退，不改 trace。
- 基线：437 passed（2026-08-27 实测 17s）。

## Task 1：AST 架构测试守硬约束第 8 条

**Files:** Modify `tests/architecture/test_service_boundaries.py`、`agents/writing/editor.py`、
`agents/writing/extractor.py`、`agents/writing/planner.py`、`services/outline_service.py`、
`services/volume_review.py`、`agents/writing/validator_agent.py`

1. 加第 6 个检查项 `test_production_does_not_hardcode_novel_format`：AST 层禁止 `Compare` 两侧
   同时出现 `novel_format` 和格式名（字面量或 `NOVEL_FORMAT_*` 常量）。
2. 白名单三处，都是必须按格式名走的：`services/workflow_registry.py`（策略解析本身）、
   `services/creative_profile.py`（从创作档案派生格式）、`services/prompt_loader.py`（模板种子）。
3. 跑一次，把命中清单记下来 —— 它就是本 Task 的修复清单。
4. 逐个改成 `is_short_form_workflow()` 或相应的策略表面查询。`editor.py:51` 优先。
5. `agents/writing/validator_agent.py:111` 的 `category="zhihu_short"` 硬编码同时修掉 ——
   它让克隆短篇的工作流永远读不到自己那份 `validator_review_full_story`，尽管
   `services/workflow_admin_service.py:268-269` 确实复制了它。
6. 跑 `tests/architecture/ -q`、`test_v43_production_surface_snapshot.py`、golden trace。

## Task 2：Validator 判定语言统一

**Files:** Modify `services/validation_constants.py`、`services/short_form_surfaces.py`、
`worker_support/generation_validator_policy.py`、`worker_support/validation.py`、
`worker_support/generation_validation_flow.py`、`worker_support/generation_editor_flow.py`；
Create `tests/worker_support/test_short_form_validator_policy.py`

1. 先写测试：短篇 `viewpoint` / `payoff` 的 block 触发内容重试；短篇 `pacing` 的 block 落进
   observe-only 而不进 errors；长篇三者行为与现状逐字节一致。确认失败。
2. 把 `_V5_RETRYABLE_CATEGORIES` 移到 `services/validation_constants.py` 改名
   `RETRYABLE_CATEGORIES`（与 `FACT_CONFLICT_CATEGORIES` 同类归位），`worker_support` 从
   `services` 导入 —— 方向合法，且让 `short_form_surfaces` 能引用同一基线。
3. 新增 `retry_categories` 表面。短篇实现 = `RETRYABLE_CATEGORIES | {"viewpoint", "payoff"}`。
   长篇不注册 → 让路 → 基线不变。
4. `requires_content_retry(result)` 加可选参数 `novel_format=None`（缺省走长篇基线，保守）。
   逐个更新 11 个调用点，`novel_format` 从调用点已有的 `novel` 对象取。
5. `worker_support/validation.py:117` 的 `is_long_webnovel` 硬比删掉，story_issue 分流对所有
   工作流生效（集合与长篇一致，见「已定的取舍」）。检查 `NOVEL_FORMAT_LONG_WEBNOVEL` 导入是否
   还有别的用途。**这会改变克隆自长篇的自定义工作流的行为** —— 它们此前拿不到分流，属于修复。
6. 前端唯一例外：`frontend/src/utils/streamingJsonParser.js:185` 的长篇硬比一并改掉，否则短篇的
   story_issues 传到前端会退化成 errors/warnings，第 5 步的修复在界面上看不到。
7. 跑新测试 + golden trace + V43 快照 + 全量。

## Task 3：Editor / Validator / Extractor 的交接包与契约投影

**Files:** Modify `services/short_form_surfaces.py`、`agents/prompt_hints.py`、
`agents/writing/editor.py`、`agents/writing/validator_agent.py`、`agents/writing/extractor.py`；
Modify `tests/services/test_workflow_surface.py`

1. 照搬 `writer_context_policy()`（`agents/prompt_hints.py:590-604`）的形状，新增
   `agent_context_policy(agent_type, novel_format)` 表面：返回是否抑制
   `chapter_handoff_context` / `chapter_contract_context`。
2. 短篇实现：Editor / Validator / Extractor 三家都抑制。理由与 Writer 同 —— 那两份 payload 是
   跨章物品/证据账本机制（`item_states`、`evidence_states`、`completed_event_ledger`、
   `end_state_boundary`），短篇 planner 一个都不产出，投影全是空壳加长篇语汇。
3. 三个 agent 在入口清空 context 字段，**不在拼接处加 if** —— 与 `writer.py:71-74` 同款，
   下游注入点自动变空。
4. Planner 那两处（`planner.py:168-169`）本轮不动：它的 `contract_hint` 走的是另一条
   「产出契约」的路径，不是「消费上一章契约」，语义不同，单独评估。
5. 补 `test_workflow_surface.py` 断言：短篇下三家的 handoff/contract 投影为空，长篇下非空。
6. 跑 V43 快照（长篇必须零变化）+ golden trace + 全量。

## 执行结果（2026-08-27）

三个 Task 全部落地。测试 437 → 450 passed，V43 黄金快照与 20 条 golden trace 零变化，
`frontend` lint 与 build 通过。

**Task 1** 的 AST 检查项实际命中 7 处，比预估多一处 `worker_support/validation.py:117` ——
它同时是 Task 2 第 5 步的目标，所以提前在 Task 1 一并改掉，否则加了检查项就留一个红：

| 位置 | 改法 |
|---|---|
| `agents/writing/editor.py:51` | 删掉多余的格式名硬比，只留 `editor_policy` 的格式轴判定 |
| `agents/writing/extractor.py:51` | `not is_short_form_workflow(...)` |
| `agents/writing/planner.py:70` / `:251` | 同上 |
| `services/outline_service.py:224` | 同上 |
| `services/volume_review.py:82` | 同上，顺手删掉该文件里已无使用者的本地 `NOVEL_FORMAT_LONG_WEBNOVEL` |
| `worker_support/validation.py:117` | 删掉 `is_long_webnovel`，story_issue 分流对所有工作流生效 |

`agents/writing/validator_agent.py` 的 `category="zhihu_short"` 硬编码（AST 检查抓不到它 ——
那是关键字参数不是比较）改成由调用方传 `category`。

**这里挖出一条本不在计划里的技术债**：`validator_review_full_story` 只存在于
`prompts/validation/zhihu_short_validation.json`，长篇那份里没有这个名字，而
`services/volume_review.py:141` 的**长篇卷级通读也调用同一个方法** —— 长篇的卷报告一直在用
短篇的审校维度（开篇承诺、伏笔公平性、情绪曲线、信息密度、结尾兑现）。本次只把这个事实
显式化（`volume_review` 显式传 `NOVEL_FORMAT_ZHIHU_SHORT` 并注明原因）；给长篇写一份卷级
专用模板是独立的一件事，会新增提示词 = 改生产行为，需要单独更新黄金快照。

**Task 2** 的 `requires_content_retry` 实际只有 2 个调用点（不是 codegraph 报的 11 个 ——
那把 import 也算进去了）：`generation_validation_flow.py:199`、`generation_editor_flow.py:418`。
`RETRYABLE_CATEGORIES` 移到 `services/validation_constants.py`，新增 `retry_categories` 表面，
8 个新用例在 `tests/worker_support/test_short_form_validator_policy.py`。

**Task 3** 发现一个有利的副作用：`previous_ending_for_prompt`（`agents/prompt_hints.py:709`）
在交接包非空时刻意返回空串（避免与 `handoff.exact_ending` 重复粘贴），为空时回落到完整的
上一节结尾。所以抑制交接包不会让短篇丢掉「上一节结尾」，反而把它换成了更直白的形状。
4 个新用例在 `tests/services/test_workflow_surface.py`。

## 仍然没做的（按发现顺序，不按优先级）

- **前端那批**：`OutlineSkeletonVisual.jsx:10` 的双判定（格式名 + 中文 key 嗅探，而 `关键伏笔`
  恰好也是长篇默认伏笔 key）、`SystemConfigs.jsx` 选不了 `surface_strategy`（只能靠克隆继承）、
  `SystemConfigs.jsx:346` 的 `slice(5)` 应为 `slice(0,5)` 导致质量维度提示恒空、
  `WorldOutlineTab` 不看 `isShortOutline` 而按 `世界设定` 是否数组嗅探。前端零测试框架
  （`frontend/package.json` 里没有 vitest），补框架是笔独立投资。
- **长篇卷级通读用短篇模板**（见「执行结果」里那条技术债）。
- **Planner 的 `continuity_contract_hint`**（`planner.py:168-169`）：它走「产出本章契约」那条路，
  与三个消费方语义不同，本轮刻意不动。
- **`build_chapter_contract` 无格式轴**：本次论证为不必改（Task 3 做完后短篇路径上没有消费者），
  但结论依赖「三家都抑制 + 简报已裁剪」这两个前提，哪天有新消费者出现要重新评估。
- **记忆策略的权威来源分歧**：`services/memory_manager.py:85` 直接 `from_format(...)`，绕过
  `pipeline_configs.policy` —— 在系统配置页改 `bypass_short_term_memory_window` 对记忆装配无效。
- **`quality_gate_minimums` 没有生产消费者**：`short_form_surfaces.py` 注册了，但
  `services/quality_metrics.meets_quality_gate` 只在 `tests/test_provider_and_experiment.py` 被调用。
- **`prompt_hints.py:545-549` 研究轴先于格式轴解析**：带 `ExperimentContext` 跑短篇时短篇表面被
  整体旁路，拿到长篇研究 hint。两条轴的叠加顺序是设计决策，需要单独讨论。
- **`authority_boundary_hint()` 与 `CHARACTER_FACT_SOURCE_RULES` 仍无格式轴**：五家 / 四家全量
  注入，其中 `prompt_hints.py:110` 引用的 `required_events` 在短篇 planner 的 schema 里不存在。
- **短篇 5 个 agent 的 prompt 快照**：`tests/test_v43_production_surface_snapshot.py:136` 固定
  `novel_format="long_webnovel"`，短篇只有相对长度断言，没有逐字节锁定。

## 验证

每个 Task 结束都要过：`tests/architecture/ -q`、`test_v43_production_surface_snapshot.py`、
`tests/worker_support/test_generation_trace.py`、全量 `pytest -q` 回到 437+ passed。
Task 2 第 6 步后另跑 `cd frontend && npm run lint && npm run build`。


