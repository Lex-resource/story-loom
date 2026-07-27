# Long and Short Writing Model Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make long-form and short-form projects use practical, distinct creation parameters, context strategies, planning structures, and review behavior.

**Architecture:** Keep `novel_format` as the backwards-compatible prompt-routing key and add a JSON `creative_profile` to represent independent author choices. Reuse the chapter pipeline, but give short stories full-manuscript context and a completion review while protecting long-form creative contracts during rolling outline optimization.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React, pytest, Vitest/build tooling.

---

### Task 1: Creative profile and format-aware defaults

**Files:**
- Create: `services/creative_profile.py`
- Create: `tests/services/test_creative_profile.py`
- Modify: `models/novel.py`
- Modify: `services/project_service.py`
- Modify: `services/chapter_views.py`
- Create: `alembic/versions/<revision>_add_creative_profile.py`

1. Write tests for short and long default normalization and legacy fallback.
2. Run `pytest tests/services/test_creative_profile.py -q` and confirm failure.
3. Implement the profile normalizer and JSON model field.
4. Persist the normalized profile on creation and return it from project/status APIs.
5. Run the focused tests and migration import check.

### Task 2: Format-aware creation experience

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/CreateProjectModal.jsx`
- Modify: `frontend/src/utils/constants.js`
- Modify: `frontend/src/App.css`

1. Replace the internal-format selector with story length, publishing mode, prose style, and point-of-view controls.
2. Apply short defaults of 3 sections and 12000 total characters; apply long defaults of 100 chapters and 3000 characters per chapter.
3. Change labels and prompt guidance based on selected length.
4. Run `npm run build` from `frontend`.

### Task 3: Full prior manuscript context for short stories

**Files:**
- Modify: `services/novel_constants.py`
- Modify: `worker_support/context.py`
- Modify: `agents/pipeline_context.py`
- Modify: short planning, writing, and validation prompt JSON files
- Create: `tests/worker_support/test_short_story_context.py`

1. Write a test proving short stories receive all prior chapter content within a fixed character budget.
2. Implement a deterministic manuscript-context builder that trims oldest content only when necessary.
3. Pass the context through `PipelineContext` and expose it to Planner, Writer, Editor, and Validator prompts.
4. Run context and prompt-template tests.

### Task 4: Short-story completion review

**Files:**
- Create: `services/short_story_review.py`
- Create: `tests/services/test_short_story_review.py`
- Modify: `worker_support/merger.py`
- Modify: `prompts/validation/zhihu_short_validation.json`
- Modify: `services/prompt_loader.py`

1. Write tests for final-section detection, manuscript assembly, and non-blocking review-flag persistence.
2. Add a `validator_review_full_story` prompt covering promise/payoff, foreshadowing, emotional arc, repetition, and ending closure.
3. Trigger the review after the target section publishes; store the report as a `short_story_full_review` flag.
4. Ensure review failures do not roll back chapter publication.

### Task 5: Long-form creative contract and volume plan

**Files:**
- Modify: `prompts/planning/long_webnovel_planning.json`
- Modify: `frontend/src/components/workspace/WorkspaceOutline.jsx`
- Modify: `tests/agents/test_prompt_templates.py`

1. Extend skeleton and optimization prompts with `创作契约` and `卷纲` schemas.
2. Add outline editor sections for the contract and volume plan using existing outline update patterns.
3. Add prompt-contract tests and run the frontend build.

### Task 6: Protect the long-form contract during optimization

**Files:**
- Modify: `services/outline_service.py`
- Create: `tests/services/test_outline_contract.py`

1. Write tests showing optimizer output cannot change protected contract fields or the original title.
2. Implement a pure merge helper and apply it before saving optimized outlines.
3. Run outline service and generation tests.

### Task 7: Integrated verification

**Files:**
- Modify only files required by failures.

1. Run focused backend tests for services, prompts, worker context, and outline generation.
2. Run the frontend production build.
3. Run the broader pytest suite if focused verification passes.
4. Review `git diff` to ensure unrelated existing changes remain untouched.
