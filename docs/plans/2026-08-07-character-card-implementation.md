# Character Card Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add AI-generated, user-editable character cards as the canonical character source, with database-persisted read-only character manifests, sparse per-chapter state history, relationship data, and direct Planner/Writer integration.

**Architecture:** Keep the existing five-stage chapter pipeline. Add a character domain inside the current FastAPI/SQLAlchemy application: `CharacterCard` stores the current author-facing card, change records and pre-change snapshots provide audit/rollback, `CharacterChapterState` stores only chapters where state changed, and `CharacterManifest` is a deterministic database projection used by Planner and the graph UI. Do not add a dedicated per-character prose-writing Agent in this phase; Planner owns chapter-level character goals and Writer uses full cards for prose generation.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, PostgreSQL JSON/UUID fields, existing ChromaDB/vector outbox, React 19, Zustand, existing vis-network graph UI.

---

## Scope and invariants

- `CharacterCard` is the only editable semantic source for a character.
- The current card is overwritten in place; history is outside the card.
- `CharacterCardChangeRecord` links one modification to one pre-change snapshot. Do not put audit prose such as `reason` into AI-facing card data.
- `CharacterChapterState` is append-only after a published chapter and is created only when canonical state changes. No row is required when a character is unchanged.
- `CharacterManifest` is stored in PostgreSQL, read-only in the UI, and generated deterministically from card/state/relationship data. AI never edits it.
- Existing `character_state` living-doc APIs become a compatibility/read-only projection, not an independent source of truth.
- Planner reads manifests and produces chapter character goals. Writer reads full cards for involved characters. No new character Agent is required.
- Mainline is the only implemented storyline in phase 1; the schema reserves `storyline_id`/arc identity for phase 2 side arcs.

## Task 1: Define the character domain contracts

**Files:**
- Create: `services/character_types.py`
- Create: `services/character_schemas.py`
- Modify: `services/knowledge_types.py`
- Modify: `services/knowledge_patch_models.py`
- Modify: `services/document_constants.py`

1. Define the card sections: identity, appearance, personality, background, abilities, speech style, behavior patterns, relationships, knowledge boundary, growth route, main/side arcs, and constraints.
2. Define Pydantic input/output models with tolerant handling for legacy `CharacterKnowledge.attributes`.
3. Define change records, sparse chapter state, relationship state, and manifest DTOs.
4. Add a canonical `storyline_id` value of `main` for current chapters and keep it optional in public responses until side arcs are implemented.
5. Extend extractor output contracts with structured character state and relationship changes without exposing audit metadata to prompts.
6. Run `python -m compileall agents services models worker_support` and inspect model import cycles before adding persistence.

## Task 2: Add database tables and migration

**Files:**
- Create: `models/characters.py`
- Modify: `models/__init__.py`
- Create: `alembic/versions/<generated>_add_character_card_domain.py`
- Modify: `models/projects.py` only if a relationship is needed from `Novel`

1. Add `CharacterCard` with `project_id`, stable/current card JSON, current dynamic state JSON, status, importance, last appearance, and timestamps.
2. Add `CharacterCardSnapshot` with immutable full card JSON, checksum, and creation timestamp.
3. Add `CharacterCardChangeRecord` with `character_id`, `before_snapshot_id`, changed field paths, before/after patch JSON, effective chapter, and timestamp. Do not add natural-language `reason` to the card or prompt payload.
4. Add `CharacterChapterState` with `character_id`, `storyline_id`, `chapter_index`, state JSON, changed fields, checksum, and source reference. Add a uniqueness constraint for character/storyline/chapter.
5. Add `CharacterRelationship` with directed perspectives, relation type, status, attributes, validity chapters, and timestamps. Keep graph edges as a derived view.
6. Add `CharacterArc` with character, storyline, arc type, anchor/target chapter, status, and arc metadata. Implement storage now; defer side-arc generation to phase 2.
7. Add `CharacterManifest` with one current row per character, manifest JSON, checksum, and `generated_at`. Make it read-only through the API.
8. Generate and review the Alembic migration, then run it against a disposable local database. Do not alter existing rows yet.

## Task 3: Implement card writes, snapshots, and deterministic manifests

**Files:**
- Create: `services/character_card_service.py`
- Create: `services/character_manifest_service.py`
- Create: `services/character_state_service.py`
- Create: `services/character_relationship_service.py`
- Modify: `services/knowledge_patch_service.py`
- Modify: `services/knowledge_merger.py`

1. Implement `create_character_card`, `update_character_card`, `get_character_card`, and `list_character_cards`.
2. In `update_character_card`, lock/read the current card, save one full pre-change snapshot, overwrite the current card, create one change record, rebuild the manifest, and commit atomically.
3. Implement field-path patching with validation for required sections and protected invariants such as impossible status transitions or invalid chapter numbers.
4. Implement `get_state_at_chapter` by selecting the newest sparse state with `chapter_index <= requested_chapter`; treat absent rows as inherited state.
5. Implement `apply_chapter_state_changes` with semantic hash comparison so unchanged characters do not receive duplicate rows.
6. Implement relationship upsert/update atomically with card/state changes, preserving directional perspectives and chapter validity.
7. Implement `build_manifest` as pure deterministic code. It may summarize structured fields by rules, but must not call an LLM.
8. Ensure manifest generation only reads card/state/relationship data and never includes change logs or snapshots.

## Task 4: Migrate legacy character knowledge

**Files:**
- Create: `scripts/migrate_character_cards.py`
- Modify: `services/living_docs_service.py`
- Modify: `services/knowledge_settings.py`
- Modify: `services/living_docs.py`
- Modify: `services/knowledge_merger.py`

1. Read existing `character_state` entries through the current `CharacterKnowledge` parser.
2. Map known legacy fields into the new card sections and preserve unknown fields under a clearly marked legacy extension field.
3. Create an initial card snapshot and current manifest for every migrated character.
4. Make migration idempotent by skipping characters already linked to a `CharacterCard`.
5. Change `character_state` reads to return the generated manifest projection for compatibility.
6. Reject direct writes to the character-state living document with a clear API error, or route supported structured edits through `CharacterCardService`.
7. Keep old files/backups recoverable until migration has been manually verified.

## Task 5: Add AI card generation and user editing APIs

**Files:**
- Create: `agents/character_card_agent.py`
- Create: `routers/characters.py`
- Modify: `main.py`
- Modify: `services/outline_service.py` if seed/outline extraction is reused
- Modify: `prompts/planning/long_webnovel_planning.json` only if card-generation prompts are colocated there

1. Add an AI generation command that creates initial cards from project seed, outline, genre, style, and existing character hints.
2. Validate generated JSON against the card schema and repair/retry malformed output using existing JSON recovery conventions.
3. Add API endpoints for listing manifests, reading a full card, generating initial cards, patching a card, reading sparse state history, and reading change records.
4. Keep manifest endpoints read-only; there is no manifest edit endpoint.
5. User card edits must use the same transactional service as AI updates, including pre-change snapshot and manifest rebuild.
6. Never pass `CharacterCardChangeRecord` or `CharacterCardSnapshot` data into generation prompts.

## Task 6: Feed manifests to Planner and cards to Writer

**Files:**
- Create: `services/character_context.py`
- Modify: `worker_support/context.py`
- Modify: `worker_support/generation_planner_flow.py`
- Modify: `worker_support/generation_writer_flow.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `prompts/planning/long_webnovel_planning.json`
- Modify: `prompts/writing/long_webnovel_writing.json`
- Modify: `prompts/validation/long_webnovel_validation.json`

1. Add `build_planner_manifest_context` that loads only current database manifests and relevant open threads.
2. Add manifest context to Planner input so it can choose chapter characters and generate each character's chapter goal.
3. Preserve the existing `characters_involved` outline field as the selection contract between Planner and Writer.
4. Add `build_writer_character_context` that loads full cards, latest state at `chapter_index - 1`, relevant relationships, and hard constraints only for selected characters.
5. Keep the context bounded: selected characters first, direct relationship neighbors second, no full-project card dump.
6. Add the same selected-character context to Editor and Validator so existing nodes enforce voice, motivation, knowledge, ability, and timeline constraints.
7. Do not create a character Agent planning loop. If a card conflicts with the chapter outline, return a normal validation/outline issue for the existing retry path.

## Task 7: Update cards and sparse states after extraction

**Files:**
- Modify: `agents/writing/extractor.py`
- Modify: `services/knowledge_merger.py`
- Modify: `services/knowledge_patch_service.py`
- Modify: `worker_support/generation_postprocess.py`
- Modify: `worker_support/events.py`

1. Extend extractor instructions to emit only observed character changes, relationship changes, and arc progress; it must not invent unchanged fields.
2. Validate extracted changes against the card schema and frozen facts before applying them.
3. Apply dynamic card updates, sparse chapter-state rows, relationship changes, manifest rebuilds, and vector outbox entries in one database transaction.
4. Skip `CharacterChapterState` insertion when the canonical state hash is unchanged.
5. Preserve existing high-risk extractor review behavior for hard continuity conflicts.
6. Publish an event that identifies changed character names and chapter index without streaming audit metadata.

## Task 8: Use canonical relationships for the graph and retrieval

**Files:**
- Modify: `services/knowledge_character_graph.py`
- Modify: `services/knowledge_graph_builders.py`
- Modify: `services/knowledge_query_service.py`
- Modify: `services/vector_settings_index.py`
- Modify: `services/vector_retrieval.py`
- Modify: `services/knowledge_filtering.py`
- Modify: `frontend/src/components/knowledge-graph/graphTransforms.js` only if response shape changes

1. Build character graph nodes from current cards/manifests and edges from structured `CharacterRelationship` rows.
2. Keep a legacy fallback for old `CharacterKnowledge.attributes.relationships` until migration is complete.
3. For Planner retrieval, index compact manifests and open relationship/arc summaries.
4. For Writer retrieval, retrieve full selected cards and relevant state/relationship chunks.
5. Do not index change logs, before snapshots, or audit fields as writing knowledge.
6. Verify graph output remains compatible with existing `vis-network` transforms.

## Task 9: Make the frontend reflect the new authority model

**Files:**
- Create: `frontend/src/pages/Characters.jsx`
- Create: `frontend/src/components/characters/CharacterCardEditor.jsx`
- Create: `frontend/src/components/characters/CharacterManifestPanel.jsx`
- Create: `frontend/src/components/characters/CharacterStateTimeline.jsx`
- Modify: `frontend/src/pages/LivingDocs.jsx`
- Modify: `frontend/src/services/novelApi.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/knowledge-graph/*` as required by API response changes

1. Add a read-only manifest/personnel view for fast browsing and Planner context visibility.
2. Add a separate full character-card editor for user edits.
3. Add a read-only state timeline showing chapters where the character changed.
4. Add change-record viewing and rollback actions without exposing audit data to generation prompts.
5. Remove or disable the raw textarea editor for the `character_state` living document.
6. Show relationship and main/side arc summaries from the card domain.

## Task 10: Phase 1 verification and rollout

**Files:**
- Modify: `README.md`
- Modify: `docs/database-operations.md`
- Create: `docs/plans/2026-08-07-character-card-rollout.md` only if operational notes need separation

1. Run the migration on a copy of an existing project database.
2. Run the legacy migration script and compare character counts, names, aliases, and relationships before/after.
3. Manually verify: AI card generation, user edit, pre-change snapshot, current-card overwrite, manifest refresh, and rollback.
4. Manually generate a chapter where one character changes and one does not; verify only the changed character receives a chapter-state row.
5. Verify Planner receives manifests and Writer receives full selected cards, while change logs are absent from prompts/log streams.
6. Verify the graph uses structured relationships and the existing graph UI still renders.
7. Verify a hard continuity conflict still enters the existing review/pause path.
8. Update README with the new data authority and the read-only nature of人物志.
9. Do not add a cloud test suite in this feature; use focused local smoke checks and existing project checks only.

## Deferred phase 2: character side arcs

After phase 1 is stable, use the already-created `CharacterArc` and `storyline_id` fields to add side-arc generation. A side arc should use the character's last mainline state as its anchor, read mainline facts through the target chapter, write to separate branch chapters, and never mutate mainline chapters directly. Merge back only through conflict analysis and an explicit merge operation.

## Acceptance criteria

- A project can generate and persist complete AI-created character cards.
- Users can edit cards; the current card is overwritten, while a one-to-one pre-change snapshot and change record remain available.
-人物志 is database-backed, deterministic, read-only, and derived from card/state/relationship data.
- Planner uses manifests; Writer uses full cards for selected characters; no character Agent loop is added.
- Character state history is sparse and chapter-addressable.
- Relationship graph and retrieval use canonical structured relationship data.
- Existing chapter generation, extractor review, living-doc rollback, and vector outbox behavior remain intact.
