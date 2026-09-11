# 2026-08-29 第三轮全量复审发现清单

复审范围：三轮改造（死代码删除 → S1-S18 稳定性 → 运行时控制三阶段）之后的全部代码。客观基线：pytest **535 passed**（60s，主因是 test_shared_http 的真实 SSL 构造 ~9s + 架构 AST ~4s）、前端 vitest 7 passed + build 通过。上轮 8 项遗留 **7 项已修**（含代际标记修孤儿串扰、/health/storage 挂 warmup、参数删行回默认），仅死常量半修。新代码稳定性无高危问题。

## A. 新积累的死代码（约 400 行，均高置信零引用）

| 文件 | 规模 | 说明 |
|---|---|---|
| services/knowledge_settings.py | 199 行 | 孤儿，唯一提及是历史计划文档 |
| services/knowledge_world_rules.py | 77 行 | 孤儿 |
| services/knowledge_foreshadowing_timeline.py | 43 行 | 孤儿 |
| services/knowledge_plot_tracks.py | 43 行 | 孤儿 |
| services/watchdog_stats.py + tests/services/test_watchdog_memory_stats.py | 49+行 | 运行时死代码，测试按路径读源码钉住，**须成对删** |
| services/vector_constants.py:16-18 | 3 常量 | VECTOR_QUERY_TEXT_MAX_CHARS / VECTOR_OUTBOX_BATCH_SIZE / DEFAULT_VECTOR_OUTBOX_MAX_RETRIES |
| services/stream_constants.py:5-7 | 3 常量 | STREAM_STEP_PAUSED / STREAM_STEP_SYSTEM / STREAM_PLACEHOLDER_CHAPTER |
| config.py:39 APP_NAME + .env.example:12 | 字段 | FastAPI title 硬编码，无读者（中置信） |

注：vector_constants.py:17-18 是上轮遗留⑧的未修半截。config 其余 9 个 LLM/调度字段都被 PARAM_SPECS 引用为默认值，**在用，勿删**。

## B. 稳定性新发现（无高危）

1. **（中）experiment_recorder 阻塞 flush 进事件循环**：`_flush_pending_writes`（experiment_recorder.py:93-97）用 `concurrent.futures.wait` 同步等待，但被异步上下文调用（generate_job_runner.py:351 的 deactivate、experiment_publication.py:36 → record_published_chapter，且后者持 `_publication_record_lock` 期间阻塞）。大快照（几十 MB）落盘时冻结进程秒级——正是 S5/S6/S7 修掉的那类问题的残余形态。修法：flush 也下放 executor 线程（或把 deactivate/record_published_chapter 改 async 化走 `asyncio.wait`）。
2. **（低）两处无锁读微窗**：`runtime_tunables_service.py:231-241` `_load_rows` 在持 `_cache_lock` 下"先全回默认再覆盖"，并发 `get_value_sync`（不持锁）可能瞬时读到 default（单次、自愈）；`vector_chroma.py:213` 读 `_op_started_at` 与 executor 线程置 None 的微窗可让 `TypeError` 替换 `ChromaTimeoutError`（仅错误类型失真）。
3. **（低）ensure_fresh 持锁做无超时 DB 查询**（runtime_tunables_service.py:191-206）：DB"挂死"形态（非报错）时所有异步 get_value 在锁上无限排队。可给戳查询包 `asyncio.wait_for`。

## C. 前端

1. **lint 现在是红的**：`Workspace.jsx:23` `API_BASE` prop 已无人使用（App.jsx:22/:705 传入死 prop），`npm run lint` 报 1 error——删 prop 即绿。另 eslint 关掉了 exhaustive-deps，正是轮询竞态没被拦的原因，建议恢复为 warn。
2. **WorkerRuntimeView 错误态**（SystemConfigs.jsx:773-785）：轮询失败每 4s 弹一个 toast（4.5s 存活 ≈ 常驻轰炸）；首拉失败永久 spinner 无重试按钮。建议加 error 态 + 状态翻转时只提示一次。
3. **dist 堆了 5 代陈旧 hash 产物**（32 个文件）：outDir 未清空，手动清一次并核查 emptyOutDir。
4. **SystemConfigs.jsx 972 行拆分方案**：RuntimeTunablesView（614-763）与 WorkerRuntimeView（765-972）自包含可先抽（-358 行）；再抽 WorkflowSettings/Toggle/Meta，页面剩约 300 行；`asErrorList` 提为 utils/errorFormat.js（RuntimeTunablesView:666-669 手写重复了它）。
5. **轮询可合并**：WorkerRuntimeView（4s）与 ConsoleLogs（5s）两套实现不会同时挂载（无双倍请求），但建议抽 `useWorkerStatus` hook 统一清理与错误策略。
6. **一致性小债**：useProjectData.js:32 与 projectApi.list 重复定义同一端点；WorkerRuntimeView 手动 reload 无 seq 守卫（旧响应可覆盖新状态，useProjectData 有先例）。
7. **仍欠**：prettier 47 文件未格式化（故意留作独立提交）；vitest 仅 streamingJsonParser 一个文件（outlineModel.js 纯函数最值得补）。

## D. 文档漂移（5 处）

1. `CLAUDE.md:16` 测试数 531 → **535**。
2. `CLAUDE.md:124` "49 条路由" → routers/ 实为 **88** 条（含 main.py 直挂 92）。
3. `README.md:137-148` routers 树：列出**不存在的 living_docs.py**，缺 character_branches/novel_memory/worker_admin。
4. `README.md:134` worker.py 注释建议补"外部模式薄壳（默认不用）"。
5. `services/system_configs_service.py:235` 注释仍是"独立 worker 有 5 分钟 TTL 缓存"——已是版本戳热生效，应改。

## E. 测试性能

- `tests/services/test_shared_http.py` 两用例 ~9s 全耗在真实 `httpx.AsyncClient` SSL 上下文构造（实测 1.6s/个）——monkeypatch 构造器或注入共享 SSLContext 可砍到毫秒，全量 60s → ~51s。
- test_vector_chroma_timeout 的真实 sleep 合计 ~1.4s，是超时机制必要等待，可接受。

## F. 历轮未变事项（非代码）

- **300+ 文件仍未提交、无备份**（168??/28D/134M）——持续是最大风险，状态全绿正适合分域提交。
- 仓库卫生原样：根目录 4 个 worker 日志、logs/ 110MB、.claude/worktrees/ 5.2MB（objective-antonelli 里那份 backlog 文档先抢救）、.codegraph 11MB、requirements.txt 与 pyproject 重复 + tiktoken/python-dotenv 未删。

## 建议处理顺序

1. 文档 5 处 + lint 红（半小时内的小活，先让门禁变绿）
2. A 死代码一批删（删完跑全量 pytest）
3. B1 flush 阻塞 + E 测试提速（一起做）
4. C 前端：dist 清理 + prettier 独立提交 + SystemConfigs 拆分 + WorkerRuntimeView 错误态
5. B2/B3 两个微窗 + ensure_fresh 超时（顺手）

---

## 验收记录（实施后复核）

客观基线：pytest **534 passed in 15.34s**（60s → 15s，shared_http SSL 构造已修）；lint 绿；git 删除条目 28 → 33（与 A 清单吻合）；534 = 535 - watchdog 测试成对删除，自洽。

| 项 | 状态 | 证据 |
|---|---|---|
| A 死代码 8 项 | ✅ 全删 | 6 文件不存在；6 个死常量 + APP_NAME grep 零命中 |
| B1 flush 阻塞 | ✅ 修得比建议更彻底 | 新增 `adeactivate`/`aflush_pending_writes`（flush 下放 to_thread），生产调用点全部切换（generate_job_runner.py:351、batch_runner.py:93）；`arecord_published_chapter` 把整个读-改-写连同步 flush 一起下放单线程（experiment_recorder.py:515-535），experiment_publication/chapter_service/knowledge_merger 调用链全走 async 版；同步版 docstring 明示仅测试/研究脚本用 |
| B2a tunables 微窗 | ✅ | `_load_rows` 整表重建 fresh dict 后原子换引用（runtime_tunables_service.py:233-244），同步读点只见旧或新快照 |
| B2b chroma 微窗 | ✅ | 局部快照读消除 TOCTOU（vector_chroma.py:213-216，注释点明原因） |
| B3 ensure_fresh 无超时 | ❌ 未修 | runtime_tunables_service.py:191-206 仍持 `_cache_lock` 做无 wait_for 的 DB 查询（低severity，DB 挂死形态才触发） |
| C1 lint 红 | ✅ | `npm run lint` 零错误（死 prop 已删） |
| C2 WorkerRuntimeView 错误态 | ❌ 未修 | reload 失败仍每 4s 弹 toast（WorkerRuntimeView.jsx:17-19），首拉失败仍永久 spinner 无重试按钮（:74-81） |
| C3 dist 陈旧产物 | ✅ | `emptyOutDir: true` 显式配置 + 注释（vite.config.js:8-9），assets 32 → 8 |
| C4 拆分 | ✅ 大部分 | SystemConfigs 972 → 594，抽出 RuntimeTunablesView(155)/WorkerRuntimeView(213)/FormControls(22)；errorFormat.js 未建（asErrorList 重复仍在） |
| C5 useWorkerStatus 合并 | ❌ 未做 | 建议项，无影响 |
| C6 seq 守卫/重复端点 | ❌ 未做 | 建议项 |
| D 文档 5 处 | ⚠️ 3修2错 | README living_docs ✅、worker.py 注释 ✅、system_configs_service.py:235 旧注释 ✅；**CLAUDE.md:124 "57 条路由"仍错**（实测 app.routes = 95 HTTP + 1 WS = 96，是把旧的 49 加了 8 个新端点）；**CLAUDE.md:16 "全量 ~10s" 不实**（实测 15.3s；534 个用例这个数对） |
| E 测试提速 | ✅ | 60s → 15.34s |
| prettier | ➖ 维持未格式化 | 47 → 50 个文件（新文件未跑），仍留作独立提交 |

**结论：A/B1/B2/C1/C3/C4/E 七项验收通过，其中 B1 的实现（整个读-改-写下放线程）优于原建议。开放项：D 的两个数字、B3、C2 错误态，外加三个可选项（errorFormat/useWorkerStatus/seq 守卫）与 prettier 独立提交。**

### 尾项复核（同日第三轮收尾）

上述全部开放项已关闭，独立验证如下（pytest **536 passed in 13.66s**，lint 绿，vitest 7 passed，build 384ms）：

- **D 两处数字** ✅：CLAUDE.md:16 "536 个用例,全量约 10-15s 视机器"（实测 536/13.7s，诚实区间）；:124 "92 条路由(91 HTTP + 1 WebSocket)"（实测 app.routes 95 HTTP − main.py 直挂 4 条 = 91，加 1 WS，准确）。
- **B3 ensure_fresh 双超时** ✅：锁获取 0.5s（`_REFRESH_LOCK_TIMEOUT_SECONDS`，等不到锁直接用旧快照）+ 刷新查询 5s（`_REFRESH_DB_TIMEOUT_SECONDS`，wait_for 包裹，超时后 TTL 重启防紧循环）；锁语义正确——acquire 超时未持锁不 release，持锁路径全分支（含 TTL 早退）走 finally release。配两个新测试 `test_db_hang_bounded_and_falls_back_to_snapshot` / `test_lock_busy_returns_stale_immediately`（534→536 的 +2）。
- **C2 错误态** ✅（超建议）：首拉失败 → 错误面板 + 手动重试按钮；轮询失败 → 陈旧横幅"最后已知状态，每 4 秒自动重试"而非 toast 轰炸；仅用户主动操作失败才 toast。
- **可选项三项全做** ✅：`utils/errorFormat.js`（asErrorList 提取，4 处消费）；`hooks/useWorkerStatus.js`（共享单例轮询：首订阅者启动/末订阅者停止、最新值缓存、**seq 守卫内置**、错误交订阅方决定展示）；ConsoleLogs(5s) 与 WorkerRuntimeView(4s) 均已接入。
- **prettier 50 文件** ➖：维持"留作独立提交"策略，未变。
- **C6 残留** ➖：useProjectData.js:32 与 projectApi.list 仍各定义一次 `/writing/projects`（一致性小债，随下次前端改动顺手收）。

**第三轮清单至此全部关闭（除 prettier 独立提交与两处非阻塞小债）。**

### 最终收尾（同日第四查）

- **prettier** ✅：全量格式化完成，`--check` 全过；`.prettierrc`（singleQuote/semi/trailingComma/printWidth 120/lf）就位；并新增组合门禁 `npm run check` = format:check + lint + build 一条命令。
- **C6 重复端点** ✅：useProjectData.js 改走 projectApi.list，`/writing/projects` 全库单一定义。
- 终态基线：后端 **536 passed**（13.4s）；前端 lint 零错误、vitest 7 passed、build 383ms、prettier 全过。
- **未了事项**：①全部改动（152M/33D/171??）仍未做任何本地提交——prettier 原计划的"独立提交"也未执行，格式化混入了工作区；②vitest 仍仅 streamingJsonParser 一个文件，outlineModel 补测建议仍开放；③注意远端 origin 是公开 GitHub 仓库（story-loom），本分支含未开源的新版本代码，**不应推送到该远端**（仅 main 已推送的第一版本）。
