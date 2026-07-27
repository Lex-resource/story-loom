# Prompt Template Consistency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复长短篇提示词、代码传参与磁盘种子之间的不一致，确保短篇校验、短篇大纲交互、提示词初始化和 writer 动态调控都稳定可用。

**Architecture:** 运行时仍以数据库 `prompt_templates` 为准，磁盘 `prompts/` 作为新环境种子。代码层补齐必要变量传参和模板回退策略，数据层同步修复现有数据库记录与 JSON 种子，测试层增加模板完整性、占位符匹配和关键短篇流程覆盖。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL/SQLite-compatible tests, pytest, React/Vite only for optional UI smoke.

---

### Task 1: Add Prompt Placeholder Contract Tests

**Files:**
- Modify: `tests/agents/test_prompt_templates.py`
- Modify: `tests/services/test_settings_modules.py` only if a reusable fixture is needed
- Reference: `agents/writing/validator_agent.py`
- Reference: `agents/writing/planner.py`
- Reference: `agents/writing/writer.py`

**Step 1: Write failing tests**

Add tests that assert:
- `[zhihu_short][validator_validate_content]` must not require placeholders that `ValidatorAgent.validate_content` cannot provide.
- `[zhihu_short][planner_generate_chapter_outline]` system prompt must not contain literal `{{` or `}}`.
- `[zhihu_short][planner_generate_skeleton_outline]` has `type == "planning"`.
- Short prompt set includes `planner_chat_modify_outline`, `planner_optimize_skeleton_outline`, and `planner_review_act_rhythm` or the code has an explicit fallback path.

Example helper:

```python
import re

def placeholders(text: str) -> set[str]:
    return set(re.findall(r"(?<!{){([a-zA-Z_][a-zA-Z0-9_]*)}(?!})", text or ""))
```

**Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py -q
```

Expected before fixes: failures for short validator variables, double braces, and/or short template availability.

---

### Task 2: Fix Short Validator Context Variables

**Files:**
- Modify: `agents/writing/validator_agent.py:42`
- Modify DB row: `prompt_templates(name='validator_validate_content', category='zhihu_short')`
- Add seed JSON row if missing in: `prompts/validation/zhihu_short_validator.json`
- Test: `tests/agents/test_prompt_templates.py`

**Step 1: Choose one canonical variable contract**

Use the existing code-friendly variables for both long and short:
- `active_entities_context`
- `previous_ending`
- `content`
- optional `title`, `genre`, `style`

Do not keep short-only `{global_outline}` and `{short_term_context}` unless code passes them explicitly everywhere.

**Step 2: Update code defensively**

In `ValidatorAgent.validate_content`, pass additional aliases so old DB rows do not silently blank out during rollout:

```python
global_outline=context.global_outline,
short_term_context=active_entities_context,
```

Keep existing `active_entities_context` too.

**Step 3: Update DB prompt**

Replace short validator user template with:

```text
【作品信息】
小说标题：{title}
小说类型：{genre}
作品风格：{style}

【当前有效设定与活文档上下文】
{active_entities_context}

【上一章结尾】
{previous_ending}

【需要校验的正文】
{content}
```

**Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py -q
```

Expected: placeholder contract test passes.

---

### Task 3: Add Short Planner Templates Or Implement Explicit Fallback

**Files:**
- Modify or add seeds:
  - `prompts/planning/zhihu_short_planner_tools.json`
- Modify DB rows:
  - `planner_chat_modify_outline / zhihu_short`
  - `planner_optimize_skeleton_outline / zhihu_short`
  - `planner_review_act_rhythm / zhihu_short`
- Optional Modify: `agents/writing/planner.py:148`, `agents/writing/planner.py:174`, `agents/writing/planner.py:193`
- Test: `tests/agents/test_prompt_templates.py`

**Step 1: Prefer adding real short templates**

Create short-specific templates instead of falling back to long prompts. Short story behavior differs enough that long templates may over-expand outlines.

**Step 2: Seed `planner_chat_modify_outline`**

Prompt intent:
- Keep current short outline schema.
- Apply only requested user changes.
- Preserve chapter count and compact pacing unless user asks otherwise.
- Output JSON only.

**Step 3: Seed `planner_optimize_skeleton_outline`**

Prompt intent:
- Reconcile finished chapters and active docs into the skeleton.
- Preserve short-story compactness.
- Strengthen hook, conflict, reversal, and ending payoff.
- Output JSON only.

**Step 4: Seed `planner_review_act_rhythm`**

Prompt intent:
- Review all chapter outlines for short-story rhythm.
- Identify weak hooks, missing reversals, slow chapters, or unresolved payoffs.
- Output JSON diagnostics.

**Step 5: Update `REQUIRED_PROMPT_TEMPLATES`**

In `services/prompt_loader.py`, add short entries if these features are considered supported:

```python
("planner_chat_modify_outline", NOVEL_FORMAT_ZHIHU_SHORT),
("planner_optimize_skeleton_outline", NOVEL_FORMAT_ZHIHU_SHORT),
("planner_review_act_rhythm", NOVEL_FORMAT_ZHIHU_SHORT),
```

**Step 6: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py tests\worker_support\test_generation_outline.py -q
```

Expected: all required short planner templates exist.

---

### Task 4: Normalize System Prompt JSON Examples

**Files:**
- Modify DB row: `prompt_templates(name='planner_generate_chapter_outline', category='zhihu_short')`
- Modify: `prompts/writing/zhihu_short_chapter_outline.json`
- Optional Modify: any seed JSON that has `{{` or `}}` in `system_prompt`
- Test: `tests/agents/test_prompt_templates.py`

**Step 1: Replace double braces in system prompts**

Change examples like:

```json
{{
  "chapter_index": 1
}}
```

to:

```json
{
  "chapter_index": 1
}
```

System prompts are not formatted in planner chapter-outline generation, so they must use literal single braces.

**Step 2: Keep double braces only in templates that are formatted**

If a system prompt is intentionally passed through `safe_format`, either:
- keep escaped braces and add a comment/test documenting it, or
- remove the need for formatting by moving variables to user prompt.

Prefer normalized single-brace JSON examples where no formatting occurs.

**Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py -q
```

Expected: no relevant unformatted system prompt contains `{{` or `}}`.

---

### Task 5: Complete Disk Prompt Seeds

**Files:**
- Add: `prompts/planning/long_webnovel_planner.json`
- Add: `prompts/planning/zhihu_short_planner_tools.json`
- Add: `prompts/writing/long_webnovel_writer_editor.json`
- Add: `prompts/writing/zhihu_short_writer_editor.json`
- Add: `prompts/validation/long_webnovel_validation.json`
- Add: `prompts/validation/zhihu_short_validation.json`
- Add: `prompts/extraction/long_webnovel_extraction.json`
- Modify: `services/prompt_constants.py` if `planning` or `validation` directories are not included
- Test: `tests/services/test_prompt_loader.py` or new file

**Step 1: Inspect prompt category dirs**

Check `services/prompt_constants.py` for `PROMPT_CATEGORY_DIRS`. Ensure it includes every seed directory used:

```python
PROMPT_CATEGORY_DIRS = ("planning", "writing", "validation", "extraction")
```

**Step 2: Export current DB prompts to seed files**

Use a one-off script under `scratch/adhoc_tests/` or a short Python command to dump current DB prompts into grouped JSON files.

Important:
- Do not overwrite UI-owned DB rows during normal app startup.
- Disk seeds are for missing rows only.
- Ensure all `REQUIRED_PROMPT_TEMPLATES` are present on disk.

**Step 3: Add loader test**

Create a temporary empty test DB/session and call `seed_prompts_to_database`.
Assert all entries in `REQUIRED_PROMPT_TEMPLATES` exist after seeding.

**Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_prompt_loader.py -q
```

Expected: clean DB seed test passes.

---

### Task 6: Fix Prompt Type Classification

**Files:**
- Modify DB row: `prompt_templates(name='planner_generate_skeleton_outline', category='zhihu_short')`
- Modify: `prompts/writing/zhihu_short_skeleton.json` or move it to `prompts/planning/zhihu_short_skeleton.json`
- Test: `tests/agents/test_prompt_templates.py`

**Step 1: Set DB type**

Set short skeleton type to:

```text
planning
```

**Step 2: Move or correct seed file**

Preferred: move the seed file to `prompts/planning/zhihu_short_skeleton.json`.

Acceptable: keep file location but set JSON `"type": "planning"`; loader already uses explicit `type` if present.

**Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py -q
```

Expected: short skeleton type test passes.

---

### Task 7: Improve Short Writer Dynamic Controls

**Files:**
- Modify DB row: `prompt_templates(name='writer', category='zhihu_short')`
- Add/Modify seed: `prompts/writing/zhihu_short_writer_editor.json`
- Test: `tests/agents/test_prompt_templates.py`

**Step 1: Update short writer system prompt to consume existing code variables**

Use variables already passed by `WriterAgent.write_chapter`:
- `{book_type}`
- `{book_style}`
- `{narrative_stage}`
- `{blacklist_hint}`
- `{word_count_instruction}`

Add prompt block:

```text
【作品动态定位】
- 类型：{book_type}
- 风格：{book_style}
- 当前章节阶段：{narrative_stage}
- 避免高频 AI 腔：{blacklist_hint}
```

**Step 2: Preserve short-specific constraints**

Keep:
- first-person requirement when appropriate
- compact pacing
- each chapter has hook, reversal, or payoff
- no long-webnovel water-padding

But avoid hard-coding “百万赞知乎短文爆款作者” as the only style. Make it a default writing ability, not fixed genre.

**Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py tests\agents\test_pipeline_payload.py -q
```

Expected: short writer uses dynamic variables and no placeholder is left blank unintentionally.

---

### Task 8: Add Runtime Smoke Tests For Short Story Pipeline

**Files:**
- Modify or add: `tests/worker_support/test_generation_pipeline_prompts.py`
- Reference: `agents/writing/planner.py`
- Reference: `agents/writing/validator_agent.py`
- Reference: `agents/writing/writer.py`

**Step 1: Mock LLM calls**

Patch `call_llm_json` / `call_llm` to capture `system_prompt` and `user_prompt` without calling external APIs.

**Step 2: Exercise short functions**

Call:
- `PlannerAgent.generate_chapter_outline`
- `PlannerAgent.chat_modify_outline`
- `PlannerAgent.optimize_skeleton_outline`
- `ValidatorAgent.validate_content`
- `WriterAgent.write_chapter`

Use `PipelineContext(novel_format="zhihu_short", ...)`.

**Step 3: Assert captured prompts contain expected context**

Examples:
- validator prompt contains world state / character state / foreshadowing / plot threads.
- writer system prompt contains book type/style, blacklist hint, narrative stage.
- planner short chapter prompt contains single-brace JSON example only.

**Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/worker_support/test_generation_pipeline_prompts.py -q
```

Expected: all short prompt smoke tests pass without external model calls.

---

### Task 9: Sync Current Database And Restart Runtime

**Files:**
- No source file required unless using a checked-in migration/backfill script.
- Optional Create: `scratch/adhoc_tests/fix_prompt_template_consistency.py`

**Step 1: Apply DB backfill**

Backfill current local DB:
- Update short validator template.
- Insert missing short planner templates.
- Remove double braces from short chapter outline.
- Set short skeleton type to `planning`.
- Update short writer system prompt.

**Step 2: Verify DB**

Run a script that prints:
- required count
- missing required templates
- short planner tool existence
- placeholders by template
- double-brace system prompt status

Expected:
- no missing required templates
- no mismatched short validator placeholders
- no double braces in unformatted planner system prompt

**Step 3: Restart backend and worker**

Run:

```powershell
$root = 'C:\git\novel-assistant'
$python = Join-Path $root '.venv\Scripts\python.exe'
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and (($_.CommandLine -match 'uvicorn main:app') -or ($_.CommandLine -match 'worker.py')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1
Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -WindowStyle Hidden
Start-Process -FilePath $python -ArgumentList @('worker.py') -WorkingDirectory $root -WindowStyle Hidden
```

**Step 4: Verify runtime**

Run:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/docs -TimeoutSec 10
```

Expected: HTTP 200.

---

### Task 10: Full Verification

**Files:**
- No new files.

**Step 1: Run targeted backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agents\test_prompt_templates.py tests\services\test_prompt_loader.py tests\worker_support\test_generation_pipeline_prompts.py -q
```

Expected: all pass.

**Step 2: Run existing relevant suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\services\test_settings_modules.py tests\test_smoke_imports.py tests\worker_support\test_generation_outline.py tests\agents\test_pipeline_contracts.py -q
```

Expected: all pass.

**Step 3: Frontend smoke if prompt management UI is touched**

Run:

```powershell
cd C:\git\novel-assistant\frontend
npm run build
```

Expected: build passes.

---

### Task 11: Final Manual Acceptance

**Files:**
- No source file required.

**Step 1: Create a new short story test project**

Use API or UI:
- format: `zhihu_short`
- 3 to 5 chapters
- word count: 1000

**Step 2: Confirm short pipeline reaches validation**

Check status/logs:
- skeleton generation succeeds
- chapter outline generation succeeds
- writer succeeds
- validator prompt receives non-empty active context
- no missing template error when using outline chat modify

**Step 3: Create or continue a long story project**

Confirm no regression:
- long planner templates still load
- long writer still receives dynamic variables
- long extractor still handles formatted system prompts correctly

**Step 4: Record result**

In final handoff, report:
- tests run
- DB rows updated
- seed files added
- backend restarted
- any residual risk

