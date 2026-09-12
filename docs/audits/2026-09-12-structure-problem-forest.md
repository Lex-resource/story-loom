# 结构问题森林(2026-09-12 全项目结构审计)

> 方法:十轮扫描 —— ① 已知问题归档;② 未审区域(main/worker_support/routers/前端);③ 横切扫描
> (重复 / 异常处理 / 魔法串 / 孤儿代码);④ 因果归并;⑤ routers 全量;⑥ services 领域
> (N+1/域间倒挂/会话所有权);⑦ 并发与事务;⑧ 前端深扫;⑨ 工程组织;⑩ 对外暴露面。
> ⑤-⑩ 为补充轮,产出见树 I 与"已证伪假设"。
> 工具:AST 量化扫描、codegraph(index 4,648 节点)、定向 grep。
> 定位法:`文件:行号` 以当日工作区为准;每个问题有唯一编号,树内因果边用 `→`(引发)与 `↔`(互相强化)。
> 状态标记:✅ 已修复 / ⬜ 在案未修 / 🔵 记录在案但**不建议**动(有意设计或收益/风险比不划算)。

---

## 0. 森林总览

```
                 ┌─────────────────────────────── 已闭合(历史) ───────────────────────────────┐
                 │ 树A-旧枝: 无中立词汇层 → models倒置 / agents↔services循环 / 100+延迟导入      │
                 │ 树D-旧枝: 上帝函数 ×2 / recorder 混责 / 配置散落 / 表现层混业务  (均已修复)    │
                 └──────────────────────────────────────────────────────────────────────────────┘

  当前活树(8 棵)与其因果边:

  [A 词汇层的"强制力"缺失] ──A2 会被新代码继续复制──┐
        ↑(同根)                                    │
  [E 状态魔法串绕过枚举] ←──────────────────────────┘
  [B 编排范式二象性] ──B1→B2→B3→B4 单向引发──────→ [C 连续性域三巨石互锁]
        ↑                                                │ C4 自我强化环 ↔ C1/C2
        │                                                ↓
  [D 降级与吞没不可区分] ──D2 掩盖 B 的故障────────→ 支线/主链行为漂移
  [F 会话/配置所有权分散](独立,弱边)
  [G 孤儿代码] ←── 上轮修复的衍生(G1)
  [I 数据访问与工程卫生](独立,弱边: N+1 / 依赖三源 / 私有API跨界)
  [H 前端](健康,无行动项)
```

---

## 树 A · 词汇层存在,但没有"强制力"

**根因**:历史上没有中立词汇层(上轮已建 `core/` 并消除倒置)。但词汇层**只是存在,没有被架构测试强制使用**,于是绕过它的写法会继续繁殖。

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| A1 | 习惯性函数内延迟导入 ~30 处 | `services/pipeline_config_service.py`(11 处)、`worker_support/pipeline_runtime.py`(8)、`orchestrator.py`(7)、`system_configs_service.py`(7) 等 | 已验证**不是**循环依赖(如 `pipeline_config_service→chapter_graph` 为单向),纯习惯残留;与 `prompt_hints.py` 的 12 处**有意接缝**性质不同 | ⬜ 机械提升到模块顶部即可 |
| A2 | 绕过枚举的状态字符串 12 处 | `worker_support/generation_editor_flow.py`(`chapter.status = "draft"`)等 | `core.pipeline_vocab.ChapterStatus` 已存在,代码里却写裸字符串;`StrEnum` 成员与字符串相等,运行时无害,但重构/搜索/拼错全靠运气 | ⬜ 替换为枚举 + 加一条架构测试(禁止 `status = "` 字面量) |
| A3 | source_ref / key 模板散布 | `services/narrative_index.py:119,124,141,156,160`、`chapter_continuity.py:681` 等 | `f"chapter:{i}:..."` 家族模板在 4+ 文件各自手写,格式漂移无测试守 | ⬜ 收敛为 `core` 或单一模块的模板函数 |

**因果**:A(历史缺层)→ 曾引发倒置/循环【已闭合】;现在 A2/A3 是"词汇层缺强制力"的直接症状,且**会被新代码继续复制**(自我强化)——补架构测试是断环点。

---

## 树 B · 编排范式二象性(当前最重要的活树)

**根因**:单章主链有图执行器(`chapter_graph_runner` + `chapter_steps` 11 角色注册 + golden trace 兜底),而**支线管线是手写的平行实现**——同一种业务(按章驱动多 agent)存在两套编排范式。

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| B1 | 支线管线巨函数 | `services/character_branch_generation.py:191` `process_character_branch_job`(208 行 16 分支,全库第二大函数) | planner→writer→validator 内联展开,checkpoint/commit/广播交错 | ⬜ |
| B2 | 直接驱动 pipeline node,绕过图执行器 | 同文件 `:236,246,284`(`planner_node.run` 等) | 不经 `chapter_graph_runner`,故不吃 workflow surface/质量闸门/golden trace 的任何保护 | ⬜ |
| B3 | 场景块摘要回退表达式重复 | 同文件 `:341` ↔ `services/knowledge_merger.py`(阶段4) | `(outline.summary or content[:800])` 两处原文复制,改一处漏一处 | ⬜ |
| B4 | 支线场景块吃不到整合模型 | 由 B3 推论 | `ENABLE_SCENE_BLOCK_CONSOLIDATION` 只接在主链 merger;支线永远用 800 字硬截断 | ⬜ |
| B5 | 支线无 golden trace | 由 B2 推论 | 主链编排有 20 条序列锁定,支线重构全靠人眼 | ⬜ |

**因果链(单向引发)**:B1(巨函数)→ B2(绕执行器才好内联)→ B3(回退策略复制)→ B4(能力不对齐);B2 → B5(无 trace)。
**反身边**:B 的存在让"再加一个支线特例"的最短路径永远是往 `process_character_branch_job` 里塞分支 → B1 更大 → 与树 C4 同构的自我强化环。
**断环点**:先提取共享的"场景块摘要来源"函数(B3/B4 一起解决,零风险),再决定支线是否收编进图执行器(大动作,需先给支线建 trace)。

---

## 树 C · 连续性域三巨石互锁

**根因**:契约 schema 按提示词版本增量生长(`_build_v11_state_boundaries` / `_build_v12_evidence_surface_rules` / `_build_v40_end_state_boundary` …),且**输出被黄金快照逐字节锁定**——重构的每一步都必须证明字节不变。

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| C1 | `build_chapter_contract` | `services/continuity_contract.py:506`(237 行 8 分支,现全库最大函数) | 契约 dict 的输入装配,版本 build 函数顺序拼接 | ⬜(上轮评估:拆它要动快照锁定的输入面,暂缓) |
| C2 | `contract_prompt` | `services/continuity_contract_render.py:17`(197 行,渲染 f-string 巨块) | 已独立成 render 模块,函数本体未分段 | ⬜ 分段提取时逐字节比对快照 |
| C3 | 交接包双巨函数 | `services/chapter_continuity.py:175` `writer_execution_brief`(190 行 16 分支)、`:505` `build_chapter_handoff`(180 行 11 分支) | 主线每章热路径;与 C1/C2 消费同一批数据结构 | ⬜ |
| C4 | "改动恐惧"自我强化环 | 全域 | 快照锁 → 拆分成本高 → 新版本字段继续堆进同一文件 → 更大更不敢拆 | ⬜ 断环:为 C1/C3 先建特征测试(现有快照只锁 C2 输出),把"字节不变"的证明范围从"不敢动"变成"动了就能证明没变" |

**因果**:C1 → C2(渲染要消化大 dict);C1/C2/C3 共享数据结构 → 互相锁死;C4 ↔ C1/C2(互相强化,唯一的双向环)。
**与树 B 的跨树边**:C 域的 brief/handoff 只在主链生效,支线没有 → 主链/支线连续性行为漂移(树的下游果实)。

---

## 树 D · 有意降级与意外吞没不可区分

**根因**:项目的 advisory 哲学(recall 失败返回空、投影失败不阻塞发布)是**正确设计**,但"有意的降级"与"意外的吞没"在代码形态上完全一样,观测面无法区分。

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| D1 | 宽异常 66 处 | services/worker_support/agents/routers 全域 | `except Exception:`(无裸 `except:` ✅) | 🔵 多数是设计性降级,不建议逐个改 |
| D2 | 纯静默吞错 11 处 | `except Exception:` 后直接 `pass`/仅注释 | 降级没有留任何观测痕迹 | ⬜ 至少补 `logger.debug` 或打点 |
| D3 | 降级无统一事件标记 | 全域 | advisory 路径失败不进任何指标,生产上"记忆没生效"和"记忆正常但为空"不可区分 | ⬜ 统一 `degraded_event` 打点(与 experiment_recorder/日志打通) |

**因果**:D2/D3 → 掩盖树 B 的故障(支线某环节静默失败,外部只能看到"支线质量差"而非"支线某步没跑")→ 反过来让 B1 更难被正视。**这是全森林里唯一一棵"跨树放大器"树。**

---

## 树 E · 路由层的胖业务

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| E1 | 83 行胖路由 | `routers/characters.py` `generate_characters` | 提示合并/去重/批上限策略在 router 里;`character_card_service`(528 行)已满,策略没处放 | ⬜ 下沉为 service 函数 |
| E2 | 角色域两个大文件 | `routers/characters.py`(443 行)+ `services/character_card_service.py`(528 行) | 内聚尚可,但两者之和 ~1000 行的"角色域"没有一个清晰的面 | ⬜ 低优先 |
| E3 | 其余 routers | system_configs 18 路由/253 行等 | commit 是干净的事务边界 | 🔵 健康,保持 |

---

## 树 F · 会话与配置所有权

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| F1 | 8 处手动 `async_session()` | `chapter_publish.py`、`character_branch_generation.py`、`settings_store.py`、`worker_admin_service.py`、`runtime_tunables_service.py`、`startup_recovery.py`、`vector_embeddings.py`、`orphan_cleaner.py` | 后台/启动路径自建会话是合理的,但"谁拥有会话、事务边界在哪"没有成文约定 | ⬜ 一页 ADR 文档即可 |
| F2 | runtime_tunables 读点 | 已收敛到 `AgentBase._ensure_llm_runtime`(上轮 P7) | — | ✅ |
| F3 | settings 全局单例 + `reload_settings()` | `config.py` | pydantic-settings 常规模式,DI 化收益低风险高 | 🔵 记录在案,不建议动 |

---

## 树 G · 孤儿代码

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| G1 | `KnowledgePatchSummary` 孤儿化 | `services/knowledge_patch_models.py:70` | **上轮 P5a 删除其唯一消费点的衍生问题**——类还在,没人用了 | ⬜ 删除(顺手) |
| G2 | 上轮遗留观察 | `agents/prompt_hints.py` 832 行平铺 | hint 函数按 agent 分组的机械拆分,量大价值中 | ⬜ 低优先 |

---

## 树 H · 前端(健康,无行动项)

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| H1 | 大 JSX 文件 | `OutlineSkeletonTabViews.jsx` 635、`Workspace.jsx` 605、`App.jsx` 536 | 展示密度高但状态干净(Outline 文件 0 个 useState;Workspace 只有 2 个 handler,子组件拆分到位) | 🔵 |
| H2 | 分层纪律 | 全前端 | 组件 0 处直接 fetch;store 89 行;api 层 157 行;realtime 收敛在两个 hook | 🔵 健康 |

---

## 树 I · 数据访问与工程卫生(第 5-10 轮补充轮产出)

| 编号 | 节点 | 位置 | 说明 | 状态 |
|---|---|---|---|---|
| I1 | 逐角色 N+1 | `services/chapter_deletion.py:165` | 删除章节后的角色状态回填:循环内每个 character_id 发 2 条查询(scalar + update);N=章节角色数,通常 ≤20,量级小但模式可一条 UPDATE..FROM 消灭 | ⬜ |
| I2 | 依赖钉版三源 | `requirements.txt` + `pyproject.toml` + `uv.lock` | 前两者手工同步同一份 pin 列表,漂移风险(改一漏一);uv.lock 才是安装事实源 | ⬜ 让 pyproject 成为唯一手写源,requirements 变 `uv export` 产物或删除 |
| I3 | 跨入私有 API | `main.py`(`stream_manager._deliver`) | 应用层调用 stream_manager 的下划线方法;应给 stream_manager 提供公共投递入口 | ⬜ 顺手 |
| I4 | 已核对无问题的领域 | routers(除角色域)、vector 分层(retrieval/chroma/embedding/context_formatting 职责清晰)、workflow 四件套、with_for_update 抢占点、async 无阻塞调用、无 TODO/FIXME、alembic 单头 32 节点、测试按域组织、对外暴露面(internal broadcast 双闸 + WS access_control + 空 token 防绕过) | 记录为"已验干净",避免下轮审计重复追查 | 🔵 |

### 已证伪的假设(防止未来审计重新追查)

| 假设 | 证伪证据 |
|---|---|
| 记忆/章节大表存在无 LIMIT 全表查询 | 抽查 `chapter_continuity.py:521,538,547`、`chapter_publish.py:63,79` 等,全部 `scalar_one_or_none` 或 `.limit(30/120)` |
| async 代码存在阻塞调用 | `time.sleep/requests.*` 零命中;tokenizer 重活已走 `asyncio.to_thread` |
| services 内部延迟导入源于循环依赖 | `pipeline_config_service→chapter_graph` 等均为单向;纯粹习惯(A1) |
| 前端存在状态混乱 | Outline 635 行 0 个 useState;Workspace 2 个 handler;realtime 收敛 2 hook |
| 裸 `except:` 吞错 | 全库 0 处(66 处均为 `except Exception:`,其中多数为设计性降级,见树 D) |
| TODO/FIXME 欠账 | 仅 1 处误报(提示词文案里的"XXX") |

## 饱和声明

第 10 轮仅产出 3 个新节点(I1-I3,均为 P3 级)+ 1 组已验干净清单(I4),且没有产生任何新的因果边或新树根。**判定扫描饱和**。当前森林 = 9 棵树、~40 个节点;剩余工作量集中在树 B(支线收编)与树 C(连续性域,需先建特征测试),两者都是"已知怎么修、只差排期"的状态。


---

## 附录 · 完整台账(按严重度)

| 级别 | 编号 | 一句话 |
|---|---|---|
| P1 | B1/B2 | 支线管线绕过图执行器,手写 208 行编排 |
| P1 | C1/C4 | `build_chapter_contract` 237 行 + 自我强化环 |
| P1 | C3 | 交接包双巨函数(主链热路径) |
| P1 | D3 | 降级不可观测(跨树放大器) |
| P2 | B3/B4 | 场景块回退重复 → 支线能力缺失 |
| P2 | A1 | ~30 处习惯性延迟导入 |
| P2 | A2 | 12 处状态魔法串绕过枚举 |
| P2 | C2 | 渲染 f-string 巨块(196 行) |
| P2 | E1 | 83 行胖路由 |
| P2 | F1 | 会话所有权无成文约定 |
| P3 | A3/E2/G1/G2/D2 | 模板散布 / 角色域大文件 / 孤儿类 / hint 拆分 / 静默吞错 |
| P3 | I1/I2/I3 | 逐角色 N+1 / 依赖钉版三源 / 跨入私有 API |
| 🔵 | D1/F3/H1/I4 | 设计性降级 / settings 单例 / 前端展示密度 / 已验干净清单(不建议动) |

## 复现扫描的命令

```bash
# 巨型函数(AST)
python -c "import ast,pathlib; ..."   # 见会话记录,阈值 100 行
# 延迟导入分布
grep -rEc "^\s+(from |import )" agents services worker_support routers --include="*.py"
# 跨层依赖
grep -rln "from services" models/; grep -rln "from agents" services/
# codegraph
codegraph sync && codegraph impact <symbol> && codegraph callees <symbol>
```

> 下次复审:改完任何一棵树后,回到本文件把对应节点标 ✅ 并写上提交号;新增问题追加编号,不要复用旧号。
