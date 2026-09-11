# 长篇小说分层记忆

## 数据层

记忆分为四层，PostgreSQL 是唯一业务数据源，ChromaDB 只是可重建的向量投影。

- L0 `novel_memory_evidence`：章节正文、Extractor 原始结果和来源引用。只追加，不修改历史记录。
- L1 `novel_memory_atoms`：结构化事实、角色状态、世界规则、伏笔和剧情线候选。候选带 Evidence、章节有效范围、置信度、版本、状态和权威等级。
- L2 `novel_scene_blocks`：按剧情线、卷/幕或角色弧保存压缩摘要、状态、开放问题和近期变化。
- L3 `project_doctrines`：稳定的创作契约、风格原则和 Agent 工作规则，不保存一次性剧情事实。

所有层都按 `project_id + branch_id + storyline_id` 隔离。主线使用 `branch_id IS NULL` 和 `storyline_id=main`；支线使用自己的 branch 和 storyline。主线与支线的部分唯一索引专门处理 PostgreSQL 中可空字段的 NULL 语义。

## 权威规则

LLM 只能产生 Evidence 和 Atom 候选。角色卡、用户编辑、已发布章节、冻结事实和现有 Knowledge Patch 服务仍是 canonical authority。无冲突候选在 canonical 写入成功后才转为 `accepted`；高风险候选留在 `candidate`，人工决策可以转为 `rejected` 或 `superseded`。

Evidence 和 Atom 写入使用内容哈希及 `ON CONFLICT DO NOTHING`，重复 worker 执行不会覆盖正文、历史证据或人工修改。

## 召回与降级

`services/novel_memory_recall.py` 按 Agent 使用不同的字符和条数预算，先读取 Doctrine、当前 Scene Block、已接受 Atom 和到期伏笔。召回始终带项目、支线和故事线过滤；角色卡、上一章结尾、硬约束和现有 Chroma 召回不会被通用记忆替换。

当前默认配置：

```text
ENABLE_NOVEL_MEMORY_EVIDENCE=true
ENABLE_NOVEL_MEMORY_ATOMS=true
ENABLE_NOVEL_MEMORY_RECALL=true
ENABLE_NOVEL_MEMORY_SCENE_BLOCKS=true
NOVEL_MEMORY_CONTEXT_MODE=layered
```

Evidence 与 Atom 是独立开关。关闭 Evidence 只停止原始证据留档，仍可单独写入没有
evidence_id 的 Atom 候选；关闭 Atom 才停止结构化事实写入。角色卡的稳定 card_data
只能由初次建卡或人工角色卡 API 修改，章节 Extractor 只能更新 current_state、关系
和章节状态快照。Project Doctrine 当前只支持人工或显式管理流程更新，不由章节 Extractor
自动改写。

Recall 失败返回空记忆，主流程继续使用既有 canonical context。Scene Block 聚合失败不影响章节发布，VectorOutbox 失败可重试或重建 Chroma。

## 启用顺序

1. 保持 Evidence 开启，先观察抽取失败率、人工修正率和 Evidence 重复率。
2. 在测试项目设置 `ENABLE_NOVEL_MEMORY_RECALL=true`，只读注入 Writer/Planner/Editor/Validator 的预算内记忆。
3. 通过一个完整卷的事实命中率、时间线冲突率、伏笔召回率、上下文字符数和召回延迟评测后，再开启 `ENABLE_NOVEL_MEMORY_SCENE_BLOCKS=true`。
4. 任何异常都可关闭 Recall/Scene Block flags；PostgreSQL 中的 Evidence、Atom 和 canonical 数据不需要回滚。

## 迁移与回滚

执行：

```powershell
python scripts\migrate_db.py
```

当前记忆迁移链从 `a1b2c3d4e5f6` 开始，包含可空支线唯一性修复、Atom candidate hash 和 Scene Block content hash。生产升级前先备份 PostgreSQL；不要使用 `Base.metadata.create_all()`。Chroma 遗失时重放 `VectorOutbox` 即可，不影响 PostgreSQL 记忆事实。

## 评测口径

最小样例覆盖角色状态变化、伏笔到期、支线隔离和人工权威覆盖。上线前记录：事实命中率、时间线冲突率、伏笔召回率、召回字符数、召回延迟、抽取失败率和人工修正率。
