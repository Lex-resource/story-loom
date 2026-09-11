# Maintainability Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 收拢当前项目中最影响维护性的行为契约、API 边界、模型导出和前端实时控制逻辑，同时保持生产提示词表面、数据库 schema 和研究版本隔离不变。

**Architecture:** 保留现有 `routers -> services -> models` 和 `worker_support -> services` 的总体方向。Router 负责路径参数、HTTP 异常和响应包装；service 负责查询、领域状态变化和可复用的序列化结果，但不再依赖 FastAPI 的 `Depends`。前端把 WebSocket、轮询、流式缓冲和生成阶段联动集中到 `useGenerationRealtime`，页面组件只消费状态和动作。

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, pytest, React 19, Zustand, Vite, Vitest.

---

### Task 1: Establish the current contracts

**Files:**
- Read: `CLAUDE.md`
- Read: `tests/worker_support/test_generation_trace.py`
- Read: `tests/worker_support/test_chapter_graph_runner.py`
- Read: `worker_support/chapter_graph_runner.py`
- Read: `worker_support/generation_validator_policy.py`

**Steps:**

1. Run the focused backend tests and record the two current failures.
2. Run CodeGraph `status`, `query`, and `impact`; synchronize the stale index before source edits.
3. Treat the golden trace as the authoritative attempt-exhaustion contract: attempt 3 pauses before publish.

**Verification:** focused baseline is reproducible; no production file is edited in this task.

### Task 2: Repair backend behavior contracts

**Files:**
- Modify: `worker_support/generation_validator_policy.py`
- Modify: `tests/worker_support/test_chapter_graph_runner.py`
- Modify: `tests/worker_support/test_short_form_validator_policy.py` only if a missing regression case is needed

**Steps:**

1. Move the unknown blocking-category guard ahead of local-repair wording filters. A `block`/`error`/`fatal` issue whose category is not in the known validator vocabulary must return `True`; known categories containing local-repair terms retain their current behavior.
2. Reconcile the stale graph-runner test with the golden trace. Rename its intent to assert pause/no publish when the fixed attempt budget is exhausted, rather than changing `default_graph()` to publish a failed chapter.
3. Add a focused assertion covering both cases: unknown blocking category retries; known local-repair issue does not retry.
4. Run the focused worker tests and the generation golden trace.

**Verification:** `pytest tests/worker_support/test_chapter_graph_runner.py tests/worker_support/test_short_form_validator_policy.py tests/worker_support/test_generation_trace.py -q` passes.

### Task 3: Make issue and memory API boundaries explicit

**Files:**
- Modify: `services/issue_service.py`
- Modify: `routers/issues.py`
- Create: `services/novel_memory_service.py`
- Modify: `routers/novel_memory.py`
- Modify: `services/character_branch_service.py`
- Modify: `routers/character_branches.py`
- Create or modify: focused service tests under `tests/services/`

**Steps:**

1. Convert `services/issue_service.py` into HTTP-independent functions accepting a parsed `UUID` and `AsyncSession`. Remove `Depends`, `HTTPException`, and route-specific Pydantic request classes from it.
2. Make `routers/issues.py` own request models, project/issue ID parsing, `LookupError -> 404` conversion, and response registration.
3. Move novel-memory list/count/status queries and response shaping into `services/novel_memory_service.py`; keep status validation and HTTP error mapping in the router. Preserve exact endpoint paths and response keys.
4. Add branch setting read/update operations to `character_branch_service.py`; remove direct `Novel` queries from the branch router for those endpoints. The router remains the transaction boundary for the existing request session.
5. Add tests for service results and router-level error mapping using the project’s existing fake-session/test patterns.

**Verification:** service modules have no FastAPI dependency; targeted issue, memory, branch, and architecture tests pass; endpoint response shapes remain unchanged.

### Task 4: Make ORM exports explicit

**Files:**
- Modify: `models/__init__.py`
- Modify: `models/novel.py` only for compatibility exports that are currently omitted
- Create or modify: `tests/architecture/test_model_exports.py`

**Steps:**

1. Replace wildcard imports in `models/__init__.py` with explicit imports for all ORM model classes.
2. Preserve the existing public model names used by application imports, including memory, character, branch, workflow, and runtime-tunable models.
3. Add a small export test that checks the expected model names and prevents accidental wildcard reintroduction.

**Verification:** model import tests, all service imports, and `pytest tests/architecture/ -q` pass.

### Task 5: Extract frontend generation runtime

**Files:**
- Create: `frontend/src/hooks/useGenerationRealtime.js`
- Create: `frontend/src/utils/streamingRuntime.js`
- Create: `frontend/src/utils/streamingRuntime.test.js`
- Modify: `frontend/src/App.jsx`

**Steps:**

1. Extract from `App.jsx` the WebSocket message routing, RAF stream buffering, parser lifecycle, watchdog timer, generation polling, and project-switch cleanup into `useGenerationRealtime`.
2. Keep data fetching in `useProjectData` and user-triggered mutations in `useGenerationActions`; pass those stable service functions into the new runtime hook.
3. Extract only pure, reusable stream helpers (pending-buffer factory and source-to-style mapping) into `streamingRuntime.js`, keeping behavior unchanged.
4. Leave navigation, modal state, header rendering, and action wiring in `App.jsx`; return the runtime state needed by `Workspace` so no UI behavior changes.
5. Add Vitest coverage for the pure helpers and run lint/build before proceeding.

**Verification:** `npm run lint`, `npm test -- --run`, and `npm run build` pass; `App.jsx` no longer contains WebSocket routing or RAF buffer implementation.

### Task 6: Final verification and documentation alignment

**Files:**
- Modify: `CLAUDE.md` only if the test-count wording is stale after the added tests
- No changes: `research/`, prompts, migrations, generated data/logs

**Steps:**

1. Run focused backend tests, full `pytest -q`, frontend lint/test/build, and Python compilation.
2. Run `codegraph sync`, then query/impact for the changed runtime and service symbols.
3. Review the final diff for accidental API shape, prompt-surface, schema, or research changes.
4. Update stale test-count wording to refer to the command or current count without changing architectural instructions.

**Verification:** full backend suite passes with zero failures; frontend checks pass; CodeGraph reports the changed files synchronized.

### Task 7: Harden realtime and compatibility boundaries after review

**Files:**
- Modify: `frontend/src/hooks/useGenerationRealtime.js`
- Modify: `frontend/src/hooks/useProjectRealtime.js`
- Modify: `frontend/src/utils/streamingRuntime.js`
- Modify: `models/novel.py`
- Modify: `tests/architecture/test_model_exports.py`
- Add: `frontend/src/hooks/useProjectRealtime.test.js`

**Steps:**

1. Keep the watchdog timestamp owned by WebSocket traffic; REST fallback polling must not hide a silent or disconnected stream.
2. Ignore `open`, `message`, `error`, and `close` events from sockets that are no longer active, including queued messages during project switches.
3. Remove the unused `wsLogs` subscription from the generation runtime hook.
4. Replace the compatibility module's dynamic `__all__` with an explicit list matching its existing public model names.
5. Add focused tests for watchdog timeout semantics and stale-socket identity checks.

**Verification:** frontend tests, backend architecture tests, full backend tests, compilation, build, and CodeGraph synchronization pass.

### Task 8: Close generation-start and polling race conditions

**Files:**
- Modify: `frontend/src/hooks/useGenerationRealtime.js`
- Modify: `frontend/src/hooks/useProjectData.js`
- Modify: `docs/plans/2026-09-02-maintainability-cleanup.md`

**Steps:**

1. Reset the watchdog baseline when a new project or generation run becomes active, while keeping REST polling from updating the WebSocket timestamp.
2. Reset editor and validator parsers on every stage transition, regardless of the auto-follow UI setting.
3. Prevent overlapping fallback polls and ignore stale project-status responses across poll, WebSocket, and manual refresh callers.

**Verification:** full backend tests, frontend format/lint/test/build, Python compilation, and CodeGraph synchronization pass.

### Task 9: Standardize page request lifecycles and memory counts

**Files:**
- Add: `frontend/src/utils/requestLifecycle.js`
- Add: `frontend/src/utils/requestLifecycle.test.js`
- Modify: `frontend/src/services/novelApi.js`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/Characters.jsx`
- Modify: `frontend/src/components/characters/CharacterBranchPanel.jsx`
- Modify: `frontend/src/components/workspace/WorkspaceOutline.jsx`
- Modify: `frontend/src/components/ChapterOutlinesOverview.jsx`
- Modify: `services/novel_memory_service.py`
- Modify: `tests/services/test_api_services.py`

**Steps:**

1. Add a small request guard that aborts superseded requests and exposes an `isCurrent` check.
2. Apply the guard to provider model/test requests, character and branch list/detail requests, and outline requests.
3. Pass abort signals through the API facade while preserving existing call signatures.
4. Replace memory summary full-row loading with one SQL query using `COUNT(*)` scalar subqueries.
5. Add focused tests for guard behavior and summary count results.

**Verification:** frontend format/lint/test/build, targeted service tests, full backend tests, Python compilation, and CodeGraph synchronization pass.

### Task 10: Close remaining request and unbounded-query tails

**Files:**
- Modify: `frontend/src/services/novelApi.js`
- Modify: `frontend/src/hooks/useProjectData.js`
- Modify: `frontend/src/hooks/useGenerationActions.js`
- Modify: `frontend/src/hooks/useWorkerStatus.js`
- Modify: `frontend/src/pages/SystemConfigs.jsx`
- Modify: `services/novel_memory_service.py`
- Modify: `routers/novel_memory.py`
- Modify: `services/pipeline_commands.py`
- Modify: `services/experiment_publication.py`
- Modify: `tests/services/test_api_services.py`

**Steps:**

1. Make project, settings, worker, and system-config reads cancellable and ignore stale success/error paths.
2. Preserve dirty state when settings persistence fails and prevent older save responses from replacing newer settings.
3. Bound memory detail endpoints with validated `limit`/`offset` parameters while preserving the existing item response shape.
4. Query the newest experiment payload directly and keep a bounded legacy-error fallback.
5. Add focused regressions for request lifecycle and bounded service queries.

**Verification:** frontend format/lint/test/build, full backend tests, Python compilation, and CodeGraph synchronization pass.

### Task 11: Bound remaining history and graph projections

**Files:**
- Modify: `services/project_service.py`
- Modify: `services/knowledge_query_service.py`
- Modify: `services/novel_memory_views.py`
- Modify: `tests/services/test_novel_memory_views.py`

**Steps:**

1. Add validated `limit`/`offset` parameters to project job history while preserving the existing array response.
2. Bound knowledge-graph projection reads at the query layer and keep stable ordering for recent records.
3. Preserve legacy records with unknown chapter numbers by sorting them after numbered records.
4. Verify with the `xiaoshuo` environment so backend dependencies and async test plugins come from the same interpreter.

**Verification:** full `python -m pytest -q`, frontend format/lint/test/build, Python compilation, and CodeGraph synchronization pass.

### Task 12: Bound character graph projections

**Files:**
- Modify: `services/knowledge_query_service.py`
- Modify: `tests/services/test_api_services.py`

**Steps:**

1. Add a validated graph `limit` while preserving the existing positional database-session call shape.
2. Bound character-card, relationship, and manifest queries at the SQL layer.
3. Restrict relationships and manifests to the selected character-card IDs so truncated graphs contain no dangling edges or unrelated detail records.
4. Add regressions for graph query bounds and project job-history pagination ordering.

**Verification:** full backend tests, frontend checks, Python compilation, and CodeGraph synchronization pass.

### Task 13: Separate chapter and pipeline HTTP boundaries

**Files:**
- Modify: `services/chapter_service.py`
- Modify: `routers/chapters.py`
- Modify: `services/pipeline_service.py`
- Modify: `routers/pipeline.py`
- Modify: `tests/services/test_pipeline_service_rewrite.py`
- Add or modify: focused service-boundary tests under `tests/architecture/`

**Steps:**

1. Move chapter request models and FastAPI dependency declarations into `routers/chapters.py`; chapter service functions accept a parsed project UUID, an async session, and primitive/domain values.
2. Convert chapter not-found and validation failures into domain exceptions or `LookupError`; map them to the existing HTTP status codes in the router wrappers.
3. Move pipeline request models and dependency declarations into `routers/pipeline.py`; expose service commands for generate, pause, resume, and rewrite that accept parsed UUIDs and explicit values.
4. Move the rewrite pre-cancellation query into a reusable HTTP-independent pipeline service helper.
5. Add architecture assertions that these two service modules no longer import FastAPI or `database.get_db`.

**Verification:** chapter/pipeline tests, architecture tests, full backend tests, and Python compilation pass; route paths and response keys remain unchanged.

### Task 14: Separate project and outline HTTP boundaries

**Files:**
- Modify: `services/project_service.py`
- Modify: `routers/projects.py`
- Modify: `services/outline_service.py`
- Modify: `routers/projects.py`
- Modify: `tests/test_reliability_contracts.py`
- Modify: `tests/services/test_api_services.py`

**Steps:**

1. Move project request models and `Query` declarations into the project router.
2. Make project queries and mutations accept parsed UUIDs and plain data, with router-owned 404/400 mapping.
3. Move outline request models and path parsing to the router while preserving the existing outline response shape.
4. Keep project deletion cancellation orchestration in the router and database deletion in the service.
5. Add boundary tests for invalid IDs, missing projects, and paginated job history.

**Verification:** project/outline tests, architecture tests, full backend tests, and Python compilation pass.

### Task 15: Split high-complexity pure modules

**Files:**
- Modify: `services/continuity_contract.py`
- Add: `services/continuity_sanitizers.py`
- Modify: `services/chapter_continuity.py`
- Add: `services/chapter_handoff_formatting.py`
- Modify: `services/character_card_service.py`
- Add: `services/character_card_serialization.py`
- Modify: `services/novel_memory_recall.py`
- Add: `services/novel_memory_ranking.py`
- Add or modify: focused unit tests under `tests/services/`

**Steps:**

1. Extract pure text/time sanitizers from the continuity contract without changing the public contract functions.
2. Extract chapter handoff formatting and serialization helpers from the chapter continuity module.
3. Extract character-card payload/diff/serialization helpers while keeping persistence orchestration in the existing service.
4. Extract lexical scoring and version-collapse helpers from memory recall while retaining the public recall entry points.
5. Add import and behavior tests for the extracted helpers before removing duplicate local implementations.

**Verification:** focused continuity, chapter handoff, character, and memory tests plus full backend tests pass; each changed large module has a smaller orchestration surface.

### Task 16: Finish frontend page decomposition and compatibility cleanup

**Files:**
- Modify: `frontend/src/pages/SystemConfigs.jsx`
- Add: `frontend/src/components/system/WorkflowConfigPanel.jsx`
- Add: `frontend/src/components/system/PromptConfigPanel.jsx`
- Add: `frontend/src/components/system/RuntimeTunablesPanel.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Add: `frontend/src/components/settings/ProviderEditor.jsx`
- Modify: `frontend/src/components/workspace/outline/OutlineSkeletonTabViews.jsx`
- Add: `frontend/src/components/workspace/outline/OutlineSkeletonTabs.jsx`
- Modify: `services/constants.py`
- Add or modify: frontend and architecture tests

**Steps:**

1. Extract System Configs panels by responsibility while keeping page-level selection, loading, and mutation coordination.
2. Extract provider editing and model detail rendering from Settings while preserving dirty-state and request-guard behavior.
3. Extract outline tab rendering from the skeleton tab view without changing outline editing callbacks.
4. Replace the constants compatibility facade's wildcard imports with explicit re-exports and a tested public list.
5. Run frontend and backend architecture checks after each extraction.

**Verification:** frontend format/lint/test/build, architecture tests, full backend tests, and Python compilation pass; API paths and UI behavior remain unchanged.

### Task 17: Final maintainability audit

**Files:**
- Modify: `CLAUDE.md` only if measured counts or boundaries changed
- No changes: `research/`, prompts, migrations, generated data/logs

**Steps:**

1. Run focused and full backend tests, frontend checks, Python compilation, and `git diff --check`.
2. Re-run service HTTP-dependency, wildcard-import, direct-router-database, and large-module scans.
3. Review API response shapes, prompt surfaces, database schema, and runtime behavior for accidental changes.
4. Record remaining risks explicitly rather than adding speculative abstractions.

**Verification:** all automated checks pass and the final audit has no new high-severity maintainability or runtime findings.

## Execution Status (2026-09-03)

- Tasks 13-14 completed: chapter, pipeline, project, and outline services no longer depend on FastAPI request boundaries.
- Task 15 completed: continuity sanitizers, chapter handoff formatting, character-card serialization, and memory ranking are isolated in pure helper modules with regression coverage.
- Task 16 completed: Settings, System Configs, and outline tab coordination were decomposed into focused frontend components; the constants compatibility facade uses explicit exports.
- Task 17 verification completed: backend `580 passed`, frontend format/lint/Vitest (`15 passed`)/build, Python compilation, and `git diff --check` passed. Configuration service errors now use the HTTP-independent `ServiceError` and are mapped centrally by `main.py`.
