# 2026-08-29 稳定性修复计划

来源：全库只读代码审查（2026-08-29）。死代码删除已完成（后端 10 文件 + 前端 6 文件 + novelApi/useStore 死方法 + vis-data 依赖），删除后 450 个测试全绿、前端构建通过。本文档只覆盖**稳定性隐患**，按优先级排列，逐项给位置、问题、修法、验收标准。

## 执行约束（动worker 编排前必读）

- 改 `worker_support/chapter_steps.py`、`chapter_graph_runner.py`、`generate_job_runner.py`、`services/chapter_graph.py` 之前先跑 golden trace：`.venv/Scripts/python.exe -m pytest tests/worker_support/test_generation_trace.py -q`。序列对不上就回退（CLAUDE.md 硬约束 10）。
- resume 锚点取值域只有 5 个 agent 名，别在修调度时引入新的 `current_step` 取值（硬约束 9）。
- 每完成一项跑 `.venv/Scripts/python.exe -m pytest -q`（当前基线 450 passed）。

---

## P0 — Job 调度正确性（会产生脏数据或卡死任务）

### S1 同一 job 双跑竞态
- **位置**：`worker_support/task_registry.py:22-27`（`register()` 只 `cancel()` 旧任务不 `await`，docstring 声称会等待）；`services/pipeline_service.py:155-185`（rewrite 把 RUNNING job 复位 PENDING 供重新抢占）。
- **后果**：同 job_id 新旧 asyncio 任务短暂并发跑同一章节，交错写库。
- **修法**：`register()` 改 async，cancel 后 `await` 旧任务收尾（吞 CancelledError）；rewrite 复位前调 `task_registry.cancel(job_id)` 并等待退出。
- **验收**：新增单测——同 job_id 快速 re-register，断言旧任务完全退出后才注册新任务；golden trace 不变。

### S2 异常恢复路径缺 rollback + 任务异常无人收割
- **位置**：`worker_support/orchestrator.py:144-149`（handler 抛异常后恢复查询前无 `await db.rollback()`）；`worker_support/task_registry.py:39-44`（`reap_finished()` pop 已完成任务但从不取 `task.exception()`）。
- **后果**：DB 类失败时恢复路径自身再抛，job 永久 RUNNING、小说卡 GENERATING；逃逸异常只在 GC 时以 "Task exception was never retrieved" 出现。
- **修法**：恢复路径开头 `await db.rollback()`；`reap_finished()` 对 `task.exception()` 非 None 的任务记 `logger.error`。
- **验收**：模拟 handler 抛 IntegrityError 的单测，断言 job 行最终状态正确、错误进日志。

### S3 主部署路径缺周期孤儿清理
- **位置**：`worker.py:51` 只 gather `poll_jobs + poll_vector_outbox`；`cleanup_orphaned_jobs_periodic` 只在 `worker_support/orchestrator.py:242-248` 的 `main()` 里。
- **后果**：按 CLAUDE.md 部署（`python worker.py`）时卡死 RUNNING 行无人清理，只能重启。
- **修法**：`worker.py` 主循环加入 `cleanup_orphaned_jobs_periodic`；顺带让 `ORPHAN_CLEANUP_INTERVAL_SECONDS` 真正生效（现为死配置，orphan_cleaner.py:30 硬编码 300）。
- **验收**：起 worker 跑 10 分钟，日志出现周期清理记录；杀掉 worker 进程模拟孤儿，确认被另一实例或重启后回收。

### S4 双 worker 陷阱与启动恢复杀活任务
- **位置**：`config.py:97`（`DISABLE_IN_PROCESS_WORKER` 默认 `false`）vs `.env.example`（写 `true`）vs `start_all.bat`（无条件同时起 API 和 worker.py）；`main.py:87-110`（进程内模式下启动把所有 RUNNING job 标 FAILED，uvicorn --reload 每次热重载都会杀掉在跑任务）。
- **后果**：.env 缺该变量时 API+worker 双跑；部署态 API 重启把外部 worker 正在跑的批量生成整体标失败。
- **修法**：默认值与 .env.example 对齐（建议默认 `true`，API 默认不带 worker）；进程内模式的重置逻辑加 PID/启动时间守卫，或改为只重置超过 `STALE_THRESHOLD` 的 RUNNING 行。
- **验收**：`start_all.bat` 起全栈后日志里只有一种 worker；API 重启不触碰外部 worker 的 RUNNING job。

---

## P1 — 事件循环阻塞（worker 周期性冻结数秒，放大 S1–S4）

### S5 experiment_recorder 在 async 里跑 git subprocess
- **位置**：`services/experiment_recorder.py:161-166`（`code_snapshot()` 同步 `subprocess.check_output(["git","diff","--binary"])`），调用点 `worker_support/generation_job_batch_runner.py:72`、`generate_job_runner.py:283`。
- **修法**：`asyncio.create_subprocess_exec` 或 `run_in_executor` 包裹。
- **验收**：单测 mock 大 diff，事件循环期间心跳/其他协程不被饿死（用 `asyncio.wait_for` 探针断言）。

### S6 token 计数同步阻塞
- **位置**：`services/token_count.py:29-41` + `agents/base.py:99-100`。首次调用触发 `AutoTokenizer.from_pretrained` 磁盘加载（可达数秒），每次整段 prompt 同步 encode。
- **修法**：进程启动时预加载 tokenizer（worker 启动钩子）；encode 走 `run_in_executor`。
- **验收**：首次 LLM 调用前后无秒级停顿；token 统计数值不变。

### S7 experiment_recorder 同步文件 IO
- **位置**：`services/experiment_recorder.py:120,151,191,263`（events.jsonl 追加、整份 prompt/response JSON 落盘都在事件循环内）。
- **修法**：写入下放 executor 或单独写线程 + 队列。
- **验收**：同 S5 探针法。

---

## P1 — 外部调用与资源

### S8 HTTP client 不复用
- **位置**：`agents/llm_transport.py:79`（每次 LLM 调用含每次重试新建 `httpx.AsyncClient`）；`services/vector_embeddings.py:50` 同。
- **修法**：进程级复用 client（stream_manager 已有先例），连接池共享；注意 uvicorn --reload 下随 lifespan 关闭。
- **验收**：压测一次批量生成，TCP 连接数明显下降；无 "Unclosed client session" 警告。

### S9 embedding 调用无重试
- **位置**：`services/vector_embeddings.py:50-53`，单次尝试，一次瞬时 429 即失败。
- **修法**：复用 `agents/retry_policy.compute_retry_delay` 做小重试（2-3 次）。
- **验收**：单测 mock 首次 429 后成功，outbox 不再因瞬时故障重放。

### S10 chroma 全局锁无超时
- **位置**：`services/vector_chroma.py:29,75-78`。全局 `asyncio.Lock` 串行化全部向量操作且 executor 调用无超时，一个挂死操作冻结进程内所有向量读写（outbox worker 与 recall 共用）。
- **修法**：`asyncio.wait_for(lock_acquire, timeout=...)` + executor 调用超时；超时按"recall 失败返回空记忆"处理（CLAUDE.md：不要改成抛异常中断主流程）。
- **验收**：注入挂死的 chroma 操作，recall 与 outbox 在超时后继续工作。

### S11 vector_outbox DONE 行无限增长
- **位置**：`worker_support/vector_outbox_worker.py:113`。
- **修法**：DONE 且超过 N 天的行定期删除（复用周期清理节拍，见 S3）。
- **验收**：单测构造过期 DONE 行，一轮清理后消失。

---

## P2 — 可观测性

### S12 print 吞异常 → logger
清单（改为 `logger.exception`/`logger.error`，带上下文）：
- `agents/usage.py:36-38`（token 用量落库失败）
- `services/vector_embeddings.py:76-77`（同上）
- `agents/base.py:252-253`（备份 provider 切换失败）
- `worker_support/orphan_cleaner.py:79-80`（孤儿清理整体失败）
- `services/chapter_service.py:207-208`、`services/settings_store.py:129-130`（print 代替 logger）
- `agents/llm_responses.py:42-47`（流式 chunk 解析错误无 logger 无上下文）
- `worker_support/generation_job_batch_runner.py:175-176`（`except Exception: pass`，失败广播静默）
- **验收**：全库 grep `^\s*print\(` 生产代码零命中（tests/scripts 除外）。

### S13 慢客户端背压
- **位置**：`services/stream_manager.py:69-79`（`_deliver` 串行 `await ws.send_json` 无超时）+ `agents/broadcasting.py:21-26`；log 事件带完整 prompt/response 大 payload。
- **后果**：一个慢客户端阻塞所有订阅者，并经 `agents/llm_responses.py:117-123` 内联回调反向卡住 LLM 流消费。
- **修法**：每客户端 `asyncio.wait_for` 超时 + 超时踢出；大 payload 日志事件瘦身（截断正文）。
- **验收**：mock 一个不读 socket 的客户端，其余客户端延迟不受影响。

---

## P2 — 启动/关闭/配置

### S14 StaticFiles 挂载缺 check_dir
- **位置**：`main.py:222`。frontend/dist 不存在（新克隆/纯后端部署）时 `import main` 直接抛异常。
- **修法**：`StaticFiles(directory=..., check_dir=False)`。
- **验收**：临时改名 dist 目录后 `python -c "import main"` 成功。

### S15 shutdown 不等待
- **位置**：`main.py:131-137`。轮询任务只 cancel 不 await；在跑的 `process_job` 子任务未取消即关 stream client，残余广播协程可能重建一个永不关闭的 http client。
- **修法**：cancel 后 `await asyncio.gather(..., return_exceptions=True)`；先停 task_registry 内的任务，再关 client。
- **验收**：手动 SIGINT 一次干净退出，无未关闭 session 警告，RUNNING job 有明确恢复路径。

### S16 .env.example 与 config.py 漂移
- **位置**：config 读取但 example 未列的 27 个变量，关键项：`STREAM_INTERNAL_TOKEN`（config.py:102 注释写生产 MUST set）、`DEBUG`、`CORS_ORIGINS`、`WORKER_POLL_INTERVAL`、`MAX_CONCURRENT_JOBS`、记忆层 flags、`DISABLE_IN_PROCESS_WORKER`（方向相反，见 S4）。
- **修法**：example 按分组补齐并写清默认值语义；删除死配置 `ORPHAN_CLEANUP_INTERVAL_SECONDS` 或在 S3 中接线。
- **验收**：逐 key 对照脚本比对 config 字段与 example（可写成一个测试）。

---

## P2 — 内存

### S17 长任务会话内存单调增长
- **位置**：`worker_support/generation_job_batch_runner.py:46,97` 一个 AsyncSession 贯穿数小时批量任务 + `database.py:10` `expire_on_commit=False` 使 identity map 滞留全部已加载对象。
- **修法**：按章 commit 后 `session.expunge_all()`，或每章独立短会话。
- **验收**：批量 20 章跑完，进程 RSS 无线性增长。

### S18 短篇上下文 O(全书) 加载
- **位置**：`services/memory_manager.py:88-105`，一次 select 全部章节含 `content` TEXT 再本地截断。
- **修法**：DB 侧按字节长度过滤/截断后再取。
- **验收**：功能输出不变（golden trace + 短篇测试）；SQL 不再整表拉 content。

---

## 其他待办（非稳定性，顺带清单）

1. **文档引用不存在的脚本**：README.md 与 docs/database-operations.md 让用户跑 `python scripts/migrate_character_cards.py`，scripts/ 只有 migrate_db.py 和 reconcile_storage.py —— 补写脚本或改文档。
2. **`services/watchdog_stats.py` 半孤儿**：唯一引用是 `tests/services/test_watchdog_memory_stats.py` 按路径读源码钉住；决定"接入 /health/storage"还是"连同测试一起删"。
3. **前端**：统一 raw fetch → novelApi 封装（`WorkspaceOutline.jsx:64`、`Workspace.jsx:145`、`ChapterOutlinesOverview.jsx:11`、knowledge-graph 4 个视图）；补 prettier 与 vitest；vis-network chunk 644KB 考虑动态 import 拆分。
4. **`config.py:64` 与 .env.example 的 LLM_BASE_URL 默认不同**（deepseek vs openai），实际被 DB provider 配置覆盖，统一以免误导。

## 建议顺序

S1–S4（一个 PR，调度正确性）→ S5–S7（阻塞三件套）→ S8–S11（外部调用）→ S12–S18 按批小 PR。每批后全量 pytest + 手动跑一轮真实生成验证流式/恢复路径。

---

## 审查修正与实施记录（2026-08-29，代码审查 + 全量实施后补记）

审查阶段对照代码逐条核实了本文档，以下修正已落实到实现：

1. **S5/S7 降级**：两者都只在 opt-in 实验运行时触发（`bootstrap_experiment` 守卫 / `context is None` 即返回），不是无条件的生产阻塞点；P1 里真正的无条件阻塞是 S6（token 同步 encode）与每次新建 HTTP client（S8）。已按此认识实施。
2. **S12 清单不全**：全库 grep 实际有 17 个文件 32 处 print，清单只列了 7 处。已按 grep 全量清扫，并以 `tests/test_no_print_in_production.py`（AST 扫描）固化零 print 验收。
3. **S16 计数与 key 错误**：实际缺失 30 项（非 27）；`DISABLE_IN_PROCESS_WORKER` 在 example 里已存在，只属于 S4 的方向漂移。已按实际清点重写 .env.example 并加对照测试。
4. **新增遗漏项**：`agents/llm_payload.debug_log_payload` 在 DEBUG 开启时每次 LLM 调用同步写整份 payload，且 DEBUG 默认值是 true——比 S5/S7 更值得修。已实施：debug 写盘下放线程池，`DEBUG` 默认值翻转 false（.env.example 同步注明）。
5. **S10 简化**：recall 调用方已统一"异常→空记忆"，超时只需抛 TimeoutError，无需在 chroma 层实现降级返回。
6. **S1 依赖 S10**：register() 等待旧任务可能被卡死在不可取消的 executor 段，故 S10 超时提前到第一批实施；register 的等待另加 10s 限时兜底。
7. **S13 表述修正**：broadcasting 是 fire-and-forget 派发不阻塞调用方；实质问题是 `_deliver` 串行无超时 + 内联 chunk 回调。已改为并发投递 + 每客户端 15s 超时 + 踢出；payload 正文字段截断至 16K 字符（前端检查面板保留可用）。

实施状态：S1–S18 全部完成（S8/S9 含 embedding 小重试与共享 client；S11 DONE 行 7 天保留期每小时清理；S14 check_dir=False；S15 shutdown 有序收尾；S17 每章 expunge+merge；S18 短篇元数据先行取尾带兜底）。新增回归测试 24 个；每批全量 pytest 通过（最终 474 passed），golden trace 与架构测试始终绿色。

已知限制（超出本计划范围，后续决策）：
- 跨进程 rewrite 双跑窗口：外部 worker 模式下 rewrite 复位 PENDING 后，若部署了 2+ worker，旧任务要到下一检查点才退出；根治需要 job 行增加 run token（schema 变更）。
- run_with_chroma 的 wait_for 超时无法取消已在 executor 线程里跑的 chroma 调用，只是止损。
- 杂项 2/3（watchdog_stats 去留、前端 raw fetch 统一）未动，需产品决策。

---

## 独立验收记录（2026-08-29，实施后第三方复核）

方法：三个并行审查代理逐项对照计划核查 + 关键缺陷人工抽查复核；全量 `pytest -q` 474 passed、golden trace 24 passed、`import main` 实测通过、`.env.example` 双向对照 0 缺失 0 多余。

**结论：S1–S18 中 15 项验收通过（✅），3 项实现但有遗留缺陷（⚠️：S3、S7、S11）。附带的 4 项待办中 3 项完成，前端统一化（待办 3）未动。实现质量总体很高：S1 的 asyncio.wait + 10s 限时逃生、S10 的取舍文档化、S18 的逐字节一致兜底都是正确设计；新增 24 个回归测试含零 print AST 守卫与 env 对照守卫。**

### ⚠️ 遗留缺陷清单（建议下一批处理）

1. **S7 残留：`record_published_chapter` 读前缺 flush 屏障**（已人工复核确认）。`services/experiment_recorder.py:501` 的 `_read_experiment_events(context)` 之前没有 `_flush_pending_writes()`，违反模块自声明的不变量（:93-94 "读-改-写路径读文件前调用"）。写队列里的 `chapter_finished` 事件未落盘时，幂等判断（:502-507）可能失效导致重复追加。修法一行：:501 前补 `await _flush_pending_writes()`（注意该函数是同步 def，需按模块既有分流模式处理）。
2. **S11 残留：DONE 行 DELETE 无批量上限**（已人工复核确认）。`worker_support/vector_outbox_worker.py:44-49` 是无 LIMIT 的整表条件删除，存量百万行时首跑会形成长事务大 DELETE。修法：按主键分批（每批 5000 行）循环删。`cleanup_done_outboxes` 零测试覆盖，补一个。
3. **S3 残留：内嵌模式无周期清理**。`main.py:147-150` 内嵌 worker 分支只起 poll_jobs/poll_vector_outbox，运行期卡死 RUNNING 行无人回收（外部 worker 主路径已修好，影响面仅限非默认的内嵌模式）。修法：该分支补 `create_task(cleanup_orphaned_jobs_periodic())`。

### 小清理（顺手项）

- `worker_support/orchestrator.py:35` 死 import `cancel as cancel_task`（已复核：全文件无使用）。
- `worker_support/orphan_cleaner.py:34` 死常量 `PERIODIC_INTERVAL_SECONDS`（已复核：定义后无引用，周期循环自行重读 settings）。
- `config.py:69` 注释失实：`LLM_MODEL` 注释写 "aligned with services/settings_constants.DEFAULT_LLM_MODEL"，但实际值 `deepseek-v4-flash` ≠ `deepseek-chat`（`services/settings_constants.py:9`）。二选一：改注释或对齐值。
- S13 备注：`_slim_log_dict`（agents/broadcasting.py:20-24）非递归，嵌套结构内长字符串不会被截断。

### 测试缺口（有实现无测试的项）

S6（preload/count_tokens 兜底）、S8（shared_http 生命周期与自愈重建）、S11（DONE 清理条件与节拍）、S4（启动恢复守卫）均无专门单测；S3 的 worker.py gather 组合无测试锁定。


### 二轮修正记录（同日复审遗留项）

1. **S7 补漏**：`record_published_chapter` 的 `_read_experiment_events()` 前补 `_flush_pending_writes()`——async 上下文里事件是异步落盘的，幂等判断不 flush 会读到旧内容导致 `chapter_finished` 重复追加（唯一有真实数据影响的一项，一行修复）。
2. **S11 加固**：DONE 行删除改为按 `DONE_ROWS_PURGE_BATCH=500` 分批短事务循环删，避免存量大的首跑形成无 LIMIT 长事务；新增 `test_vector_outbox_done_purge.py`（分批、零行、中断保部分计数三用例）。
3. **S3 补漏**：内嵌 worker 模式（main.py）也接入 `cleanup_orphaned_jobs_periodic`，shutdown 一并收尾该任务；启动重置逻辑抽取为 `services/startup_recovery.reset_stale_running_jobs()`（返回 failed/fresh 计数）并补单测。
4. **小清理**：orchestrator 死 import `cancel_task`、orphan_cleaner 死常量 `PERIODIC_INTERVAL_SECONDS` 删除；config.py LLM_MODEL 的"已对齐"注释改为如实描述三级生效顺序（DB provider > settings_constants（deepseek-chat）> 此兜底值 deepseek-v4-flash）。
5. **S13 递归截断**：`_slim_log_value` 递归处理嵌套 dict/list/tuple 中的长字符串。
6. **测试缺口补齐**：S6（tokenizer 预热/兜底/metrics 语义）、S8（共享 client 复用与按请求超时）、S11、S4（陈旧重置编排）各补单测；后端总数 474 → 487。
7. **前端待办 3 落地**：novelApi 新增 `outlineApi.get`、`chapterApi.outlines/submitJsonReview`、`knowledgeGraphApi`（4 端点）；7 处裸 fetch（WorkspaceOutline、Workspace review_json、ChapterOutlinesOverview、knowledge-graph 4 视图）全部改走封装，组件不再接收 apiBase/API_BASE 透传（父组件同步清理）；`useBackendHealth` 的 /health 直连保留（带 AbortController，非业务接口）。补 prettier（.prettierrc + format 脚本）与 vitest（streamingJsonParser 7 用例）；`npm test` 7 passed、`npm run build` 通过。全库 prettier --write 格式化留作独立提交，避免与本次改动混在一起。

### 二轮复核确认（2026-08-29，第三方逐项复验）

上方"二轮修正记录"7 项**全部复核属实**，无虚报：S7 flush 屏障（experiment_recorder.py:503，单线程 executor 保序 + `concurrent.futures.wait`，同步/异步分流正确无死锁）；S11 分批短事务（500/批，选 ID 再删）+ SYNCING 孤儿恢复（计划外加固）；S3 内嵌模式接入周期清理并纳入 shutdown，启动恢复抽为 `services/startup_recovery`；死 import / 死常量 / 失实注释 / 递归截断四项小清理到位；四个测试缺口补齐（test_stability_followups 7 例、test_llm_transport_client、test_vector_outbox_done_purge 3 例）；前端 7 处裸 fetch 仅剩 api.js 封装本体与 useBackendHealth 例外，prettier + vitest 就位。

独立验证结果：后端 `pytest -q` **487 passed**（474 → 487，+13）；前端 `npm test` **7 passed**、`npm run build` 通过、全库裸 fetch grep 达标。

**至此本计划（含遗留缺陷、小清理、测试缺口、前端待办 3）全部关闭。唯一已知开放项：跨进程 rewrite 双跑窗口（见"已知限制"，需 schema 变更根治，可另行立项）。**
