# TencentDB Novel Memory Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 TencentDB Agent Memory 的分层记忆、异步沉淀、场景块和渐进召回思路适配到长篇小说创作，同时保留小说项目的事实源、时间线和人工编辑权威。

**Architecture:** 不直接引入 MemoryCore、MemoryProxy 或 SQLite 运行时。继续使用当前项目的 PostgreSQL 作为唯一业务数据源、ChromaDB 作为向量检索层，在其上增加小说领域的 Evidence、Memory Atom、Scene Block 和 Project Doctrine 四层模型。LLM 只能生成候选和摘要；角色卡、已发布章节、冻结事实和有效章节范围仍由现有领域服务控制。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, ChromaDB, 当前多智能体流水线和后台 worker。

---

## 设计边界

- `Evidence` 保存章节正文、Extractor 原始结果、生成阶段和来源引用，作为 L0 原始证据。
- `Memory Atom` 保存结构化事实、状态、事件、约束和伏笔候选，必须带来源章节、置信度、权威等级、有效章节范围和状态。
- `Scene Block` 面向卷、幕、角色弧和剧情线，保存可压缩的阶段摘要、当前状态、开放问题和关联来源；只注入摘要，全文按需读取。
- `Project Doctrine` 只保存稳定的风格、叙事和 Agent 工作规则，不保存一次性剧情事实。
- `CharacterCard`、人工修改记录、已发布章节和冻结事实不可被通用 LLM 记忆合并逻辑直接覆盖。
- 第一阶段不引入腾讯项目的 Team/ACL、MemoryProxy、Skill、Wiki 或 CodeGraph 产品面，只复用记忆协议和处理流程。

### Task 1: 建立小说记忆领域契约

**Files:**
- Create: `models/novel_memory.py`
- Modify: `models/__init__.py`
- Modify: `alembic/env.py`
- Create: `alembic/versions/<revision>_add_novel_memory_layers.py`
- Create: `services/novel_memory_types.py`
- Test: `tests/test_novel_memory_models.py`

**Steps:**

1. 定义 `NovelMemoryEvidence`、`NovelMemoryAtom`、`NovelSceneBlock` 和 `ProjectDoctrine` 的字段、索引、唯一约束和级联删除关系。
2. 为 Atom 建立 `candidate|accepted|rejected|superseded` 状态、`generated|user|published|system` 权威等级，以及 `valid_from_chapter` / `valid_to_chapter` 时间范围。
3. 为所有记忆记录增加 `source_ref`、`source_chapter`、`confidence`、`version` 和 `branch/storyline` 维度，确保主线和角色支线隔离。
4. 运行 `python scripts/migrate_db.py` 或项目约定的 Alembic 检查，确认迁移可升级、可回滚且不破坏现有表。
5. 运行 `pytest tests/test_novel_memory_models.py -q`。

### Task 2: 接入 L0 证据捕获

**Files:**
- Create: `services/novel_memory_evidence.py`
- Modify: `services/knowledge_merger.py`
- Modify: `worker_support/generation_postprocess.py`
- Modify: `worker_support/orchestrator.py`
- Test: `tests/services/test_novel_memory_evidence.py`

**Steps:**

1. 在章节提取完成后保存不可变 Evidence，记录项目、分支、章节、流水线阶段、输入摘要、原始模型输出和来源引用。
2. 对同一章节和阶段使用内容哈希幂等写入，重复 worker 执行不得产生重复证据。
3. 对已发布章节只允许追加 Evidence，不允许修改已存在正文或历史证据。
4. 验证角色支线 Evidence 不进入主线检索集合。
5. 运行 `pytest tests/services/test_novel_memory_evidence.py -q`。

### Task 3: 将 Extractor 输出变成受控 Memory Atom

**Files:**
- Create: `services/novel_memory_atoms.py`
- Modify: `services/knowledge_patch_service.py`
- Modify: `services/knowledge_merger.py`
- Modify: `services/knowledge_frozen_facts.py`
- Modify: `services/character_card_service.py`
- Test: `tests/services/test_novel_memory_atoms.py`
- Test: `tests/test_character_consistency.py`

**Steps:**

1. 将现有 Knowledge Patch 候选转换为带来源和时间范围的 Atom，不改变当前结构化知识的 canonical 写入路径。
2. 复用当前实体解析、角色卡 authority、冻结事实和章节有效范围逻辑；仅对未冲突候选执行自动接受。
3. 对同一实体和谓词实现候选去重、更新、合并、废弃四种动作；冲突时保留旧事实和新候选，不能静默覆盖。
4. 为用户编辑、已发布章节和手工锁定事实建立不可被 LLM merge 绕过的测试。
5. 运行 `pytest tests/services/test_novel_memory_atoms.py tests/test_character_consistency.py -q`。

### Task 4: 实现 L2 Scene Block 聚合

**Files:**
- Create: `services/novel_memory_scenes.py`
- Modify: `worker_support/generation_postprocess.py`
- Modify: `worker_support/context.py`
- Modify: `services/vector_settings_index.py`
- Modify: `services/vector_retrieval.py`
- Test: `tests/services/test_novel_memory_scenes.py`

**Steps:**

1. 为卷、幕、角色弧和剧情线生成可增量更新的 Scene Block，包含摘要、当前状态、开放问题、近期变化和来源章节。
2. 使用现有 worker 做异步聚合，失败不阻断章节发布；聚合任务需要幂等和可重试。
3. 通过 `VectorOutbox` 将 Scene Block 投影到 Chroma，保留项目、支线、scope 和章节范围元数据。
4. 召回时只注入 Scene Block 摘要和路径/标识，LLM 需要细节时再读取正文。
5. 运行 `pytest tests/services/test_novel_memory_scenes.py -q`。

### Task 5: 按 Agent 实现渐进召回

**Files:**
- Create: `services/novel_memory_recall.py`
- Modify: `worker_support/context.py`
- Modify: `services/vector_retrieval.py`
- Modify: `agents/prompt_hints.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/validator_agent.py`
- Test: `tests/services/test_novel_memory_recall.py`

**Steps:**

1. 统一召回接口，先并行获取稳定 Doctrine、当前 Scene Block、相关 Atom、到期伏笔和章节片段，再按 Agent 类型裁剪。
2. 为 Planner、Writer、Editor、Validator、Extractor 分别配置集中管理的条数、字符数、章节窗口和超时预算。
3. 保留上一章结尾、角色卡和到期伏笔的领域专用上下文，不让通用语义召回替换硬约束。
4. 在现有 Chroma 语义检索上补充 PostgreSQL 精确检索或 FTS，再做融合排序；不得新增 SQLite 运行时 fallback。
5. 记忆服务失败时只降级为无记忆或已有 canonical context，不能让主流程失败。
6. 运行 `pytest tests/services/test_novel_memory_recall.py tests/test_reliability_contracts.py -q`。

### Task 6: 增加评测和可观测性

**Files:**
- Create: `tests/evals/novel_memory_cases.json`
- Create: `tests/evals/test_novel_memory_quality.py`
- Modify: `services/watchdog_stats.py`
- Modify: `README.md`
- Create: `docs/novel-memory.md`

**Steps:**

1. 构造包含角色状态变化、世界规则冲突、伏笔埋设/回收、支线隔离和人工覆盖的最小长篇样本。
2. 记录事实命中率、时间线冲突率、伏笔召回率、上下文字符数、召回延迟、抽取失败率和人工修正率。
3. 对比现有上下文策略与新分层召回策略，只有在一致性不下降且 token/延迟可接受时才扩大启用范围。
4. 在文档中说明数据层、权威规则、失败降级、迁移和回滚方式。
5. 运行完整测试：`pytest -q`。

### Task 7: 分阶段启用

**Steps:**

1. 先以 feature flag 只启用 Evidence 和只读 Recall，不改变现有 canonical 写入。
2. 在测试项目上启用 Atom 候选和 Scene Block，观察至少一个完整卷的指标。
3. 通过指标确认后，再对指定 Agent 开启 Scene Block 注入；默认保留旧召回作为 fallback。
4. 每个任务完成后单独提交本地 commit；本分支只保留在本机，不执行 `git push`。

## Verification Checklist

- [ ] `<本地路径>/TencentDB-Agent-Memory` 是有效 Git 仓库，远端指向官方仓库，核心文件可读。
- [ ] `novel-assistant` 当前分支为 `codex/novel-memory-tencentdb`，且未创建或配置远端分支。
- [ ] 现有工作区改动未被 stash、reset、restore 或覆盖。
- [ ] PostgreSQL 仍是唯一业务数据源，未加入 SQLite 运行时 fallback。
- [ ] 角色卡、已发布章节、冻结事实和支线隔离规则均有测试保护。
- [ ] 新召回策略有字符/token/延迟预算和失败降级。
- [ ] 完整测试、迁移检查和质量评测通过后，才允许扩大 feature flag 范围。
