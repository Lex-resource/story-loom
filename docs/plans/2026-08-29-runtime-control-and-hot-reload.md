# 2026-08-29 运行时控制与热生效计划

四个工作流：**提示词热生效 / 运行参数入库（前端可改）/ chroma 僵尸消除 / worker 单进程综合管理**。经四路并行深探后成文。按用户要求：阶段一（提示词+参数，最简单）先行；chroma 其次；worker 整合最后。

## 0. 先澄清：SQLite 到底还在不在用

**业务数据库从来没有用过 SQLite。** `config.py:16-19` 硬校验 `DATABASE_URL` 必须是 `postgresql+asyncpg://`；全仓 `import sqlite3` 零命中。SQLite 只出现在两处，都不是我们的业务数据：

1. **ChromaDB 自己的持久化层**：`data/chroma/chroma.sqlite3`（638MB，git-ignored）是 chromadb 库内部存元数据用的，属"可重建的向量投影"（丢失后重放 VectorOutbox 即可，CLAUDE.md:150）。
2. **`.codegraph/codegraph.db`**：CodeGraph 工具的索引缓存，可删。

"僵尸操作"发生在 chroma 内部那个 SQLite 上：`run_with_chroma` 的 120s `wait_for` 超时后锁释放，但已进线程池的旧调用无法取消，与后续操作并发争抢 chroma 内部锁。这是阶段二要解决的，与业务库无关。

## 1. 阶段总览与依赖

```
阶段一（先行，最简单）          阶段二                    阶段三
提示词热生效  ──┐
                ├─ 共享 etag 基础设施 ──→ chroma 超时改走参数 ──→ worker 单进程整合
运行参数入库 ──┘   (config_versions.py)    chroma 僵尸消除         (暂停开关/超时走阶段一设施,
                                                                  chroma 已稳定可同进程承载)
```

- 阶段一产出两样公共设施：`services/config_versions.py`（表版本戳，提示词与参数表共用）和 `runtime_tunables` 表 + typed getter（chroma 超时、worker 暂停开关都吃它）。
- 全程基线：pytest 487 passed；改编排前跑 golden trace；架构测试 `services 不得 import worker_support` 是硬边界（下面方案已规避）。
- 注意 alembic 链：当前 head 是 `d4a5b6c7e8f9`，阶段一有两个迁移，**必须串链**（第一个的 revision 作为第二个的 down_revision），不能都指向 d4a5b6c7e8f9。

---

## 2. 阶段一（先行）：提示词热生效 + 运行参数入库

### 2.1 提示词热生效

**目标**：前端改提示词保存后，独立 worker 进程的下一个 agent 步骤立即用新提示词（现状：TTL 300s + 失效只作用于 API 进程）。

**关键事实**：
- 缓存是进程内 dict，键为解析后的 `(name, category)`（`agents/prompt_templates.py:63-66,80`）；`prompt_scope.resolve` 在缓存**之前**调用（`agents/base.py:66`），覆盖与缓存正交——改"何时重读"不破坏"只解析一次"约束（CLAUDE.md:114-115）。
- 调用频率 = 每个 agent 步骤一次（20 处调用点，重试复用），每章十几次，戳查询成本（几十行的表，亚毫秒）可忽略。
- `PromptTemplate` **没有 updated_at**（`models/operations.py:44-55`），需加列；运行期全部写路径走 ORM setattr+commit，onupdate 可靠（在线编辑/删除 `system_configs_service.py:219-236,283-330`，种子 `overwrite_existing=False` 不覆盖已有行，worker 不跑种子）。

**方案：组合版本戳 `(COUNT(*), MAX(updated_at))`**（推荐，弃"专用版本表"和 LISTEN/NOTIFY）：
- 组合戳的关键价值：纯 `MAX(updated_at)` 在"删除最新行"时不变，`COUNT(*)` 补上这个语义洞。写路径**零改动**=没有可漏的失效点；NOTIFY 需要池外连接+重连管理，复杂度不成比例。
- 新建 `services/config_versions.py`：`async def table_version_stamp(session, table) -> tuple[int, str|None]`，表名白名单（初值 `{"prompt_templates"}`，runtime_tunables 上线时追加）。agents 层经函数内懒 import 使用（`agents/base.py:26,30` 有模块级 import services 先例，无架构障碍——架构测试只禁 services→worker_support）。
- `agents/prompt_templates.py` 的 `load_prompt_template`：开 session 后先查戳，一致→直接命中缓存（可无视单条 TTL）；变了→全清 dict 再查库；**戳查询异常→退回现有 300s TTL 行为**（可用性优先于新鲜度，保留 TTL 作降级兜底）。键语义、`invalidate_prompt_cache`（本进程写后快速失效）均不动。

**改动清单**：
1. alembic：`prompt_templates` 加 `updated_at DateTime default=_utcnow onupdate=_utcnow`（对齐 `models/operations.py:32` Job 的写法）+ 回填 `SET updated_at = created_at`；down_revision 链见 §1。
2. `models/operations.py` PromptTemplate 加列。
3. 新建 `services/config_versions.py`。
4. `agents/prompt_templates.py` 加戳校验（保持函数内懒 import 风格 :85-87）。
5. `agents/constants.py:202-205` 注释改为"TTL 现为 DB 不可达时的降级兜底"。

**测试**（新增 `tests/agents/test_prompt_template_cache.py`）：
- 核心场景：填充缓存 → 绕过 invalidate 直接用另一 session 改库（模拟 API 进程的写，正是 worker 眼中的世界）→ 再次 load 断言读到新文本；DELETE 行→抛 ValueError（:97-101）；INSERT 新键→可读。
- 戳查询抛异常→返回旧缓存（降级语义）；TTL 300s 行为回归（`PromptTemplateCache.get/set` 的 now 参数可注入 :17/:28）。
- `tests/services/test_prompt_scope.py` 加"resolve 恰好调用一次"计数守卫（把 CLAUDE.md:114-115 从注释升级为测试）。
- 新增 `tests/services/test_config_versions.py`（UPDATE/INSERT/DELETE 后戳变化、非法表名拒绝）。
- 回归：golden trace 逐条不变（trace 不含 load_prompt_template，已验证）；V43 黄金快照不带 UPDATE 标志逐字节一致（只改读取时机，不改渲染）。
- 手工双进程验收：起 worker.py + API，前端改 writer 提示词，worker 生成下一章时 LLM 日志（`agents/base.py:151-159` 的 prompt_name）里确认新内容，无需重启。

### 2.2 运行参数入库（runtime_tunables）

**目标**：一批运维参数存数据库，前端"运行参数"页可改、快速生效；同时为 chroma 超时（阶段二）和 worker 暂停开关（阶段三）提供存储。

**存储**：新表 `runtime_tunables(key String(64) PK, value JSON, description Text, updated_at)`——不挂 system_nodes/system_doc_types（那两张是纯 id/name_zh 枚举字典，由 seed 迁移管理，混入会污染语义）；不 seed 默认行（typed getter 默认值兜底即可）。模型加在 `models/operations.py`（仿 `SystemSettings` :72-78）。

**Service**（新建 `services/runtime_tunables_service.py`）：
- `PARAM_SPECS: dict[str, TunableSpec]`（key → type/min/max/default/group/description/effective）是**单一事实源**，同时喂校验和前端元数据端点，避免两处漂移。
- `async get_value(key)`：缺行/非法回落 default 并 clamp 到 [min,max]（校验风格对齐 `_validate_pipeline_update`，`system_configs_service.py:45-99`）；写路径：pydantic 只查类型，**范围与未知 key 校验在 service**（以 PARAM_SPECS 为准），成功后刷缓存（仿 `workflow_registry.remember` :185 的写后刷新）。
- 缓存：TTL 1-5s + asyncio lock（模式照抄 `settings_store.py:26-39,81-101`，该项目"接受 5 秒级陈旧"的既有水位）+ etag 版本戳（复用 §2.1 的 `config_versions.table_version_stamp("runtime_tunables")`）。
- **同步读点的关键设计**：`task_registry.has_capacity`（:114）、`_truncate_for_log`（`broadcasting.py:14`）这类不能 await 的调用点，改读 getter 维护的**进程内快照 dict**；异步读点直接 await。测试兼容性：`tests/services/test_stream_manager_deliver.py:30` 用 `monkeypatch.setattr(...STREAM_DELIVER_TIMEOUT_SECONDS...)` 打模块属性——重构时保留可 patch 的模块级解析函数，或同步改测试。

**参数清单**（20 项，每项已核实位置/读取时机/建议范围）：

| # | key | 现值 | 位置 | 读取时机 | 范围 |
|---|---|---|---|---|---|
| 1 | chroma_lock_acquire_timeout_seconds | 60 | vector_chroma.py:83 | 每次调用 | 10-600 |
| 2 | chroma_operation_timeout_seconds | 120 | vector_chroma.py:84 | 每次调用 | 10-600 |
| 3 | chroma_zombie_threshold_seconds | 240（阶段二新增） | 同上 | 每次调用 | 120-1800 |
| 4 | embedding_max_attempts | 3 | vector_embeddings.py:20 | 每次 HTTP | 1-10 |
| 5 | embedding_retry_base_delay_seconds | 1.0 | vector_embeddings.py:21 | 每次重试 | 0.5-30 |
| 6 | embedding_timeout_seconds | 120 | vector_constants.py:20（import 绑定 :11） | 每次 HTTP | 10-600 |
| 7 | vector_outbox_done_retention_seconds | 604800 | vector_outbox_worker.py:33（**def 默认参数绑定 :40，要改**） | 每次清理 | 86400-2592000 |
| 8 | vector_outbox_done_cleanup_interval_seconds | 3600 | vector_outbox_worker.py:34 | 循环迭代 | 300-86400 |
| 9 | vector_outbox_purge_batch | 500 | vector_outbox_worker.py:37 | 每批 | 50-5000 |
| 10 | worker_claim_paused（bool） | false | 阶段三新增，claim 入口 | 每轮抢任务 | - |
| 11 | worker_poll_interval_seconds | 5 | config.py:99（orchestrator.py:241 等） | 循环迭代（已天然热） | 1-60 |
| 12 | max_concurrent_jobs | 3 | config.py:100（orchestrator.py:231、task_registry.py:114） | 循环/调用级 | 1-32 |
| 13 | orphan_cleanup_interval_seconds | 300 | config.py:101（orphan_cleaner.py:90） | 循环迭代 | 30-3600 |
| 14 | stale_job_threshold_seconds | 600 | config.py:104（**orphan_cleaner.py:32 导入时读，必改**；startup_recovery.py:29） | 清理时 | 600-7200 |
| 15 | vector_outbox_lease_seconds | 300 | config.py:105（vector_outbox_worker.py:84） | 每 worker 一次 | 60-3600 |
| 16 | stream_deliver_timeout_seconds | 15 | stream_manager.py:16 | 每次投递 | 3-60 |
| 17 | log_text_char_limit | 16000 | broadcasting.py:11 | 每次广播 | 2000-65536 |
| 18 | post_processing_timeout_seconds | 1200 | config.py:79（generation_postprocess.py:52） | 每章调用 | 120-7200 |
| 19 | llm_timeout_seconds | 180 | config.py:76（agents/base.py:45，**每节点新建 agent 时读**） | 下一章生效 | 30-1800 |
| 20 | llm_max_retries / llm_retry_delay_seconds | 3 / 5 | config.py:119-120（base.py:46,290） | 调用级 | 0-10 / 1-60 |

**读取点改造**（逐项 file:line 见上表）：导入时绑定（#14、#7 的默认参数、#6 的 import 绑定）必须改；循环迭代读改数据源后天然热生效；agent 构造级（#19/20）下一章生效。改造后 `.env` 退化为引导配置，`test_env_example_alignment` 相应调整。

**Router + 前端**：
- `routers/system_configs.py` 加三个端点：`GET /runtime-tunables/vocabulary`（下发 PARAM_SPECS 分组元数据：key/类型/范围/默认/描述/**生效时机**，完全仿 `graph_vocabulary` 模式 `workflow_admin_service.py:500-521`——前端不写死任何参数）、`GET /runtime-tunables`（当前值）、`PUT /runtime-tunables`。
- 前端：SystemConfigs 页加**页面级顶层切换**「工作流配置 / 运行参数」（现有 TABS 是"选中工作流"的子视图 :19-24、:350-369，运行参数与工作流无关，不能塞进去）；渲染按 vocabulary 分组，数字→number+min/max+提示、bool→Toggle（风格仿 `WorkflowSettings` :463-551、Toggle :553-563）；保存走 `guard`/`asErrorList`（:84-102）展示后端分项错误；`novelApi.js` 的 systemConfigApi 加 `loadTunables/updateTunables`。生效说明文案：「轮询/清理间隔下一轮循环生效；LLM 超时对保存后新建的 agent（下一章）生效；孤儿阈值下次清理生效」。

**测试**：新增 `tests/services/test_runtime_tunables.py`（缺行回落 default、越值 clamp/400、类型错误、写后 etag 变化读到新值）；PUT 未知 key/超范围→400 中文分项 detail；热生效验收：改 `worker_poll_interval` 后下一轮 sleep 生效，改 `stale_job_threshold` 后下次清理生效（原实现需重启）。

---

## 3. 阶段二：chroma 僵尸消除

**目标**：消除"超时后僵尸与后续操作并发"的问题；**保证 chroma 每次都正常可用**——写路径必须成功（outbox 最终一致），召回尽量成功，不能靠"失败返回空"了事。

**现状与挂死源**（按概率）：
1. **首次 ONNX 模型下载无限等待**——chromadb 0.5.0 内部 `requests.get` **不带 timeout**（embedding_functions.py:437），断网/半开连接时是最大的僵尸制造者（不持 SQLite 锁）。
2. ONNX InferenceSession 首建/推理卡顿（首次 `query_texts` 兜底时才触发）。
3. chroma 内部 SQLite 写事务遇磁盘/杀毒抖动（Windows）——唯一持 OS 文件锁的形态，最危险但概率最低。
- executor 是**多线程默认池**（`run_in_executor(None,...)`），僵尸与后续操作真并发；正常时全局 Lock 已串行化，僵尸只在超时后出现，窗口=僵尸剩余寿命（无上限）。
- 0.5.0 的 `PersistentClient` 是进程级单例（SharedSystemClient 缓存 System）——**client 对象无线程亲和性，换线程直接复用，不需要重建**。

**方案：专用单线程 executor + 毒线程重建 + 启动预热自检（A+C 组合）**。弃 chroma server 子进程方案（`chroma run` 虽存在，但 0.5.0 的 HttpClient 自身无 timeout 语义，且 Windows 下孤儿子进程占 data/chroma 文件锁的风险 > 收益；留作 chroma 升级 1.x 后的备选）。

**实现**（核心改动集中在 `services/vector_chroma.py`，约 100 行）：
1. 模块级 `_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chroma")`；`run_with_chroma` 改用之——所有 chroma 操作严格按序执行，**永不与僵尸并发**（SQLite 争抢消失）；保留全局 Lock + 60s 获取超时（语义向后兼容，现有 `test_vector_chroma_timeout.py` 三用例原样通过）。
2. 毒线程检测：操作 elapsed 超过 `CHROMA_ZOMBIE_THRESHOLD_SECONDS`（默认 240 = 2×操作超时，进 runtime_tunables #3）→ `shutdown(wait=False)` 旧 executor + 新建单线程 executor + `logger.warning("chroma_executor_recycled")`。僵尸线程被隔离（无法杀死但不再接活，最终自行结束）；不重建 client（单例语义下重建是空操作）。
3. **`preload_chroma()` 启动预热**（`vector_chroma.py` 新增，main.py lifespan 与 worker.py 两处各加一块，仿 `preload_tokenizer` 模式 `main.py:50-58`/`worker.py:39-48`）：① 打开 client + collection（触发 System 组装、SQLite 打开）；② `_default_embedding_function(["warmup"])` 强制模型加载/会话建立在启动期（把最大挂死源移出热路径）；③ 最小读写探针：自检集合 upsert 1 条（显式 embeddings，免 API 依赖）→ query 1 次 → delete——对齐"写必须成功"的验收。失败不阻塞启动但记健康标志。
4. 离线检查：预热时若 `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2` 缺失且无法下载（chroma 硬编码该路径，无重定向钩子），启动即明确告警"embedding 兜底不可用"，而不是等 120s 僵尸。
5. `config.py` 加 `CHROMA_ZOMBIE_THRESHOLD_SECONDS`、`CHROMA_WARMUP_ENABLED`（阶段三并入 runtime_tunables）。

**为什么能"保证每次都可用"**：写路径 = outbox 幂等重放（确定性 id + upsert，`vector_outbox_worker.py:128-135`）+ retry_count 重入队 + SYNCING 孤儿回收——僵尸隔离后新线程立即接活，单条最多损失一个 60s 排队窗口；召回 = 空记忆降级 + 可加一次立即重试（仅 executor 健康时）。**诚实边界**：僵尸若持 OS 级 SQLite 文件锁且永不释放（磁盘级 hang），单线程模型下后续操作会排队等锁超时——该场景唯一彻底解是进程隔离（方案 B），但三大挂死源（下载/推理/瞬时 IO）都不持写锁，预热又消除了第一个，残余概率很低。

**测试**：`test_vector_chroma_timeout.py` 现有 3 用例原样通过；新增 ①僵尸隔离（threshold 调到 0.05s，hang 任务→后续 TimeoutError→触发重建→新线程任务成功）②串行性（记录线程名，两个任务必须同一线程顺序执行）③超时后一次立即重试成功；`test_stability_followups.py` 加 preload_chroma 成功/失败分支。

---

## 4. 阶段三：worker 单进程综合管理

**目标**：默认单进程（FastAPI 后端直接承载 worker），不需要单独开 worker.py；同时把"暂停/介入/队列操作"做成 API + 前端可操控的能力。外部 worker 模式保留为可选（start_worker.bat 仍在）。

**关键事实**：
- 进程内模式已存在且 shutdown/startup 拓扑已就绪（main.py 内嵌分支三循环 + 有序收尾 + startup_recovery 陈旧阈值守卫）；start_backend.bat 已去掉 `--reload`。
- **双跑窗口在单进程下关闭**：rewrite 先 `cancel_and_wait`（routers/pipeline.py:36-38）再复位 PENDING，单进程注册表是全集；残留微窗有双兜底（register 对同 job_id 先 cancel 旧任务；旧任务第一个 check_paused 见非 RUNNING 即 `JobAbortedException`）。**run token schema 变更在单进程模式下不再必要**（仅当未来要 2+ 外部 worker 才立项）。
- **两套入口重复**：worker.py 与 orchestrator.main() 的三循环完全一致，差异只在预热/清理；且 **main.py:106 `from worker import ...` 会触发 worker.py 模块级副作用**（`mark_worker_process()` 把 API 进程 `IS_WORKER` 污染为 "1"、重复 configure_logging）——现存潜伏雷，必须改从 `worker_support.orchestrator` 导入。
- 单进程收益：提示词/工作流缓存一份（配合阶段一立即生效）；事件广播从"worker 经 HTTP 打回 /api/internal/broadcast"（stream_manager.py:55-64 + `_IS_WORKER`）变零跳直投，去掉 `API_INTERNAL_URL` 依赖；部署少一个进程。
- **现有可管理性缺口**：「全局暂停领取新任务」不存在（claim 无任何开关，:192-224）；无队列控制台；单个运行中 job 无取消/重试端点（CANCELLED 枚举已存在 `pipeline_types.py:31` 且状态机终态守卫已认，只是没有端点用它）。

**方案 A（推荐）：DB 开关 + 控制 API + runner 归一**，零 schema 变更拿到全部能力；控制面存 DB 使外部 worker 模式同样受益。弃 asyncio.Event 方案（重启丢状态、外部模式失效）与 run token 方案（迁移成本大、单进程下无收益）。

**改动清单**：
1. **worker 控制 API**（新 `routers/worker_admin.py` 挂 `/api/worker` + `services/worker_admin_service.py`；注意分层——DB/查询在 services，task_registry 操作在 router（routers import worker_support 合法，先例 routers/pipeline.py:12），否则撞架构测试）：
   - `GET /api/worker/status`：mode、claim_paused、队列深度（PENDING/RUNNING 计数）、活跃任务（task_registry.active_count/has_capacity）、孤儿清理间隔。
   - `POST /api/worker/pause-claim` / `resume-claim`：写 `runtime_tunables` 的 `worker_claim_paused`（bool，阶段一设施）；`claim_pending_jobs` 开头查开关（5s TTL 进程内缓存），paused 直接返回 `[]`。暂停语义 = 不领新任务，在跑任务继续到检查点——匹配"随时暂停随时介入"。
   - `POST /api/jobs/{job_id}/cancel`：`cancel_and_wait` → job 置 `CANCELLED`（枚举已存在）→ generate job 则 novel 离开 GENERATING 置 PAUSED；不动 `current_step`（保 resume 锚点语义，不引入新取值）。
   - `POST /api/jobs/{job_id}/retry`：复用 `resume_project` 复位路径（PAUSED/FAILED→PENDING、清 error、validator→writer 修锚点，`pipeline_commands.py:76-109`）。
2. **单进程为默认**：`config.py:110` `DISABLE_IN_PROCESS_WORKER` 默认翻 `"false"`（.env.example 与注释同步）；`main.py:106` 改 `from worker_support.orchestrator import poll_jobs, poll_vector_outbox`（消除 IS_WORKER 污染）；`start_all.bat` 不再启动 worker（start_worker.bat 保留为显式外部模式入口）。
3. **runner 归一**：抽 `bootstrap_worker_context()`（init_db + tokenizer 预热 + workflow_registry.refresh，worker.py:37-62 与 main.py lifespan 共用）与 `start_worker_loops() -> dict[str, Task]`（三循环建 task 返回句柄）；worker.py 瘦身为薄壳；删除 orchestrator.py:253-254 的裸 `__main__`（它连 client 清理都没有，本就不是真入口）。
4. **前端**：SystemConfigs「运行时/队列」视图（轮询 status 展示队列深度/活跃数/暂停开关 + 项目 RUNNING 列表）；Workspace 的 ConsoleLogs 面板（:52-55 已有 pause/resume 按钮行）加队列徽标；novelApi 加 workerApi 封装。

**实施顺序**（每步后全量 pytest）：
1. 纯增量：worker_admin service+router + claim 开关检查 + 扩展 `tests/worker_support/test_job_claiming.py`。
2. 行为变更：import 源修正 + 默认值翻转 + start_all.bat + 启动编排测试（顺手补 worker.py gather 组合无测试的缺口）。
3. 纯增量：runner 归一 + 薄壳化。
4. 纯增量：前端。

**回归防线**：golden trace（本次不碰 chapter_steps/chapter_graph_runner/generate_job_runner 编排，应零变化）；`test_job_claiming.py`、`test_task_registry_race.py`、`test_vector_outbox_claiming.py`；架构测试唯一相关规则（services 不 import worker_support）已被分层设计规避。

**风险与对策**：API 重启=worker 重启，在跑任务被 startup_recovery 标 FAILED——有恢复语义但需手动 resume，可在 retry API 上补"一键恢复全部"；开发者手敲 `--reload` 会反复触发重置（README 警示）；新增代码继续守零 print/executor 纪律（`test_no_print_in_production` 会拦）。

---

## 5. 全程约束备忘

- 改 `claim_pending_jobs`/poll 循环前跑 golden trace；resume 锚点只许 5 个 agent 名（不引入新 `current_step`）。
- 每阶段结束跑：全量 pytest、`tests/architecture/ -q`、（阶段三前）`test_generation_trace.py -q`。
- 两个 alembic 迁移串链（head 当前 `d4a5b6c7e8f9`）；迁移后先 `python scripts/migrate_db.py` 再起进程（schema-at-head 强校验 `services/schema_version.py:64-67`）。

---

## 6. 验收记录（2026-08-29，实施后第三方复核）

**方法**：三个并行审查代理分阶段逐项对照计划核查（关键项人工交叉复核）+ 实测目标测试子集。客观基线：全量 `pytest -q` **531 passed**（487 → 531，+44）；前端 vitest 7 passed + build 通过；alembic 单 head 线性链 `d4a5b6c7e8f9 → f6a7b8c9d0e1 → f7b8c9d0e1a2` ✓。

| 阶段 | 结论 | 实测 |
|---|---|---|
| 一A 提示词热生效 | ✅ 6/6（组合戳确认 (COUNT,MAX)，删行语义洞已补；resolve 未挪进缓存层，"只解析一次"守卫已升级为测试） | 目标子集 30 passed |
| 一B 运行参数入库 | ✅ 7/7 ≈95%（PARAM_SPECS 21 key 单一事实源；**全部读取点动态化**，含两处"导入时读"必改点；同步读点走快照；前端 vocabulary 零写死） | 目标子集 21 passed |
| 二 chroma 僵尸消除 | ✅ 5 + ⚠️2（单线程 executor + 毒线程重建用线程侧真实起点测占用期、重建持锁无 submit 竞窗；预热自检含离线告警；zombie 阈值按备选路径落 runtime_tunables 单源，无双源） | chroma 相关 20 passed（无真实 ONNX 拖慢） |
| 三 worker 单进程整合 | ✅ 8 + ⚠️2（四端点齐、claim 开关 2s TTL 生效且不杀在跑任务、IS_WORKER 污染已修、runner 归一、架构分层守卫在） | worker_support+architecture 75 passed；golden trace 20 passed 零变化 |

**用户四点目标达成度**：① 随时暂停（全局 pause-claim + 项目级 pause 两层正交）✅ ② 随时介入（cancel/retry/status，4xx 边界齐全）✅ ③ 队列操作（可看排队/运行/活跃/在跑列表，可暂停/取消；缺口：PENDING 无明细列表、retry 未接 UI）基本达成 ④ 多线程并发（max_concurrent_jobs 1-32 入库可调、下一轮生效）✅。

### 遗留清单（全部非阻塞，按建议处理顺序）

1. `vector_chroma.py:203-204` 注释断言"重建时不可能有排队任务"不实：先前超时调用者遗留的孤儿 future 会在旧线程延迟执行并串扰 `_op_started_at`（全局单变量无锁），可能推迟下一次僵尸检出（有界 ≈2 条，低概率低危害）。修法：给 `_run_tracked` 加 executor 代际标记，或孤儿不走 tracked 路径。
2. `chroma_warmup_ok` 只写不读——建议挂进 `/health/storage`（storage_authority.py:66 现只报路径）。
3. 运行参数快照"删行不回默认"洞（`runtime_tunables_service.py:222-236` 只覆盖表内存在的 key）——与提示词侧用 COUNT 补掉的是同类问题；当前无删行代码路径，仅手删 SQL 可触发。
4. `storage_repair.py:15-18` 租约仍读静态 env 值，与 worker 侧动态读分叉。
5. `.env.example:57-58` 残留旧注释（"true…推荐"）与新默认（false=单进程）矛盾，应删（值本身正确）。
6. README/.env.example 缺 `--reload` 警示（现仅 CLAUDE.md:137 有）——单进程默认下 --reload 会丢内存任务、留孤儿 RUNNING 行。
7. 前端 `retryJob` 已封装（novelApi.js:125）但运行时视图无重试按钮。
8. 小清理：`vector_constants.py:20` 死常量、`orchestrator.py:255-261` 无人调用的 `async def main()`、GET /runtime-tunables 无 HTTP ETag 头（etag 仅内部用，可接受）、zombie 阈值与操作超时无交叉校验。

**结论：三个阶段全部验收通过，四点用户目标达成。遗留项均为打磨级，可并入下一批小修。**
