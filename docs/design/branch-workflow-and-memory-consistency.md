# 设计:支线工作流 + 主/支记忆一致性

日期:2026-09-12 · 状态:**已定稿**(用户决策完毕,见文末"最终决策")

## 背景(森林遗留 B1/B2/B5 + J2 前置讨论)

主链单章生成已由数据驱动的工作流引擎执行(`pipeline_configs` 一行 = 一个工作流:
graph JSON + surface_strategy + prompt_category + policy;`run_chapter_graph` 解释执行,
11 个角色适配器注册于 `worker_support/chapter_steps.py`)。短篇/长篇是该表的两种种子行。
**支线是唯一的手写例外**:`character_branch_generation.process_character_branch_job`
(208 行)硬编码 planner→writer→editor→validator 直调,绕过图解释器、绕过用户配置、
无 golden trace,且支线章节不产生证据/记忆原子/角色卡更新。

## 一、支线接入工作流引擎

### 绑定机制
- `character_branches` 新增 `workflow_name` 列(可空)。
- 建支线时用户可选任意 `pipeline_configs` 行;空值 = 沿用小说默认(长篇)。
- 存量支线迁移后默认长篇,行为不变。

### 执行
- 支线 job 改走 `run_chapter_graph(state, graph)`,与主线共用图解释器、11 角色适配器、
  裁决边/预算语义。
- **上下文注入是本特性核心**:适配器的记忆召回/角色卡/大纲必须来自支线域
  (branch_id 隔离、支线章节表),需要一个"支线上下文提供者",替代主线
  `MemoryManager.get_context` 在支线路径被调用的部分。
- checkpoint 沿用支线现有 `_branch_checkpoint` + 章节状态机(resume 锚点语义
  与主链 5-agent 锚点不同,保持域内自洽)。

### 安全前置
- 先为现有手写支线流程建 golden trace(冻结 checkpoint/广播/节点调用序列),
  迁移前后序列必须一致。没有这张网不动手。

## 二、主/支记忆一致性(讨论稿)

### 方向一:主 → 支(读最新,而非快照)
支线生成时的记忆召回改为"生成那一刻的最新主线已接受事实"(只读主线域),
而不是支线创建时的快照。否则主线推进后,支线会按过时状态写作,直接矛盾。
权威模型天然支持:主线 published/accepted 事实是权威,支线必须服从。

### 方向二:支 → 主(回流通道)
现状:支线事实只写支线域,主线召回永远看不到 → 支线里角色获得的物品/状态
在主线后续章节"消失"。

**方案(推荐):支线发布 → 主线域候选原子 + 人工核准**
1. 支线章节发布时,除写支线域外,同时把支线事实提取为**主线域的 candidate 原子**,
   带来源标注(来源=支线:支线名:章号),状态=candidate,authority=generated。
2. 主线后续召回时,这些候选经现有机制以【待核对记忆线索(禁止当作事实)】出现——
   AI 可见但不得当事实写。
3. 用户在记忆页(遗留二)人工核准:接受 → 主线 accepted 事实,正式生效;
   拒绝 → 不再出现。
4. 与主线后续事实硬冲突 → 现有 `novel_memory_conflicts` 队列兜底。

理由:完全复用既有权威模型("AI 只能产候选、人核准才成事实"),零新机制;
候选无害(提示词层已有"禁止当作事实"约束)。

**待拍板开关**:回流候选默认全量生成(推荐,按支线可关),还是默认关闭按需开启。

### 明确不做
- 支线事实自动转正(违背权威模型)。
- 支线域与主线域合并存储(隔离是支线的存在意义)。

## 实施顺序

1. 支线 golden trace(安全网)
2. `character_branches.workflow_name` 迁移 + 建支线 API 支持 workflow 选择
3. 支线上下文提供者 + 支线 job 改走 `run_chapter_graph`
4. trace 序列比对(迁移前后一致)
5. 主→支读最新(方向一)
6. 支→主回流候选(方向二,待用户确认开关策略)
7. 记忆 UI(遗留二,与回流的人工核准配套)


---

## 最终决策(2026-09-12,用户拍板)

**产品愿景先行**:本工具近期面向作者,远期做成**读者平台**——AI 写小说、读者看;
读者想看某配角的经历时,**由读者自己生成支线**。因此支线的定位是:锚定在主线
某一章的衍生故事,与主线正史**无关**,读者自享。

由此:

1. **支线流程:手写管线整体删除。** 支线 job 直接复用数据库里的工作流
   (`run_chapter_graph` + 小说绑定的工作流行),不新建 golden trace——
   整条替换而非迁移行为,引擎自身的 596 个测试就是保护。
2. **记忆时间锚定(方向一修正):** 支线以**创建时的锚点章号**演进——第 50 章
   创建的"第 28 章支线",用的是**截至第 28 章**的记忆,而不是最新记忆。
   实现走既有机制:记忆表本就带 valid_from/valid_to/source_chapter 章节窗口,
   支线召回以锚点章号过滤即可,零新表。
3. **无回流(方向二作废):** 支线记忆永久隔离,不向主线写候选。
   支线里的"获得物品/状态变化"只存在于支线域;主线正史不受影响。
   此前担心的"支线事实主线没体现"在读者平台定位下**不是问题,是特性**。
4. **记忆管理 UI(遗留二):** 稍后再议,与支线无关。

### 实施拆解(下一轮执行)

- **A. MemoryManager 分支模式**:`get_context` 贯穿 branch_id;查询切支线域
  (角色卡→支线表、记忆→branch 域、上一章→支线上一章),召回按锚点章号过滤。
- **B. 支线 job 改造**:handler 取小说绑定的工作流图 → 构建 ChapterRunState
  → `run_chapter_graph`;`_branch_checkpoint`/广播挂为 job 级钩子。
- **C. 删除手写管线**:`character_branch_generation` 瘦身为 handler + checkpoint +
  广播,208 行编排删除;行为与手写版对齐(仅 4 个内容节点 + 场景块,
  是否加记忆提取默认不加,与现状一致)。
- **D. 验证**:现有支线测试(test_character_branch_lifecycle 等)+ 全量套件。

---

## 增补需求(2026-09-12,二轮决策):支线是可续写的独立故事域

支线不是"一次生成即弃",而是**可连续续写**的故事域,必须有与主线同构的记忆系统:

- **锚点继承**:支线创建于主线第 N 章 → 支线继承"截至第 N 章"的主线记忆(锚点快照)
- **自主演进**:支线第 1、2、3……章发布时,在**支线域**内跑完整记忆提取管线
  (证据 → 原子 → 场景块,全部带 branch_id/storyline_id),支线自己的记忆文档
  随续写逐章累积
- **召回合成**:支线章节写作时的记忆 = 主线锚点快照(valid ≤ N,branch_id=NULL)
  ∪ 支线自身累积记忆(branch_id=支线,全部)
- **角色卡不变**:支线仍不更新主线角色卡(权威模型不变)

### 实施计划(全部完成制)

| 步骤 | 内容 | 关键文件 |
|---|---|---|
| A1 | ✅ 记忆写函数原生支持 branch_id/storyline_id(无需改动) | — |
| A2 | ✅ 支线域召回接入支线上下文(recall_novel_memory branch 模式) | character_branch_generation |
| B1 | ✅ 支线域记忆提取:ExtractorNode + 证据/原子/场景块全支线域,整合吃支线原子 | character_branch_generation |
| C1 | 支线 job 接图引擎:ChapterRunState 承载支线章节 + 小说工作流图 → run_chapter_graph | character_branch_generation + chapter_graph_runner |
| C2 | checkpoint/广播挂接为 job 级钩子 | 同上 |
| D1 | 删除手写四步编排,函数瘦身为入口+checkpoint+广播 | character_branch_generation |
| E1 | 验证:支线生命周期测试 + 全量套件;支线记忆域隔离断言 | tests |

行为对齐说明:手写版只有场景块写入支线域;新版按本计划补齐证据+原子,
这是**有意的功能增强**(用户明确要求"相同的记忆系统撑着"),非遗留行为变更。

### 实施备注(已核实,2026-09-12)

- **A1 已确认零成本**:`capture_chapter_extractor_evidence` 与 `record_patch_atoms`
  签名原生支持 `branch_id`/`storyline_id`,且 evidence 层已有支线专用
  source_ref 模板(`character_branch:{branch_id}:chapter:{n}:generation`)。
  支线域记忆写入不需要改写函数,只需调用方传参。
- **锚点快照已存在**:支线创建时 `branch.anchor_context` 已冻结主线记忆
  (角色卡/历史文档/锚点结尾),手写版 `_branch_context` 就是消费它的。
  "28 章之前的记忆"无需新做,直接沿用。
- **A2 的缺口只在"支线自身累积记忆"**:`recall_novel_memory` 已支持
  branch_id/storyline_id/chapter_index 参数,支线域召回 = 换参数调用;
  需要做的是把它接进 MemoryManager.get_context 的分支模式,并与
  anchor_context 静态文本合并。
- **C1 的真正难点(实施时证实,比预估更深)**:适配器链直接读写主线章节表
  (`get_chapter_by_index`/`save_writer_draft`/chapter_repository,11 个适配器均如此),
  不只是 MemoryManager 的上下文假设。支线走图引擎的**前置条件是先把主线章节
  访问抽象为仓库层**(有 golden trace 保护的主线路径重构,约 1-2 个会话),
  之后支线以仓库实现接入。**本轮不冒险**:支线已复用引擎的 4 个节点
  (同 agent/同提示词通道/同记忆系统),手写编排保留至仓库层重构完成。
- **B1 的边界**:支线后处理 = 证据 + 原子 + 场景块(全部 branch 域);
  跳过角色卡更新/教义同步/叙事索引/主线发布状态(权威模型不变)。
