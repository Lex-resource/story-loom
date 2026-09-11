# Current State Map

## Scope

This map describes the product branch at the start of the Ariadne research.
The Ariadne checkout is reference-only and is not imported into the product.

## Generation path

`worker_support.generate_job_runner._process_single_chapter` coordinates the
chapter path:

1. `generation_planner_flow.prepare_planner_inputs` loads `MemoryManager`
   context for `planner`.
2. `generation_outline.prepare_chapter_outline` builds a `PipelineContext` and
   calls `PlannerNode`.
3. `generation_writer_flow.load_writer_context` reloads memory for `writer`,
   adds the character manifest, normalizes the outline, and calls `WriterNode`.
4. Editor and Validator reuse the chapter context and add their own draft,
   validation, and issue fields.
5. Post-processing calls Extractor, then projects accepted character and
   layered-memory changes.

## Context ownership by agent

| Agent | Primary context | Sources and limits | Fallback/legacy behavior |
| --- | --- | --- | --- |
| Planner | global outline, handoff, chapter history, character manifest, layered recall | `MemoryManager.get_context(agent_type="planner")`; role recall budget and `context_budget_for("planner")` | Planner manifest is merged into novel memory and removed from the dedicated manifest field |
| Writer | outline, exact previous ending, handoff, contract, character context, layered recall, style | `load_writer_context`; writer memory budget, character-context budget, prompt-version compaction | `remove_authority_duplicates` removes repeated character facts from layered context; flat fields remain the Prompt API |
| Editor | draft, outline, contract, handoff, accepted facts, issue instructions | `PipelineContext` plus Editor prompt hints and review budgets | Local cleanup is preferred for non-hard issues; hard continuity failures may request a Writer retry |
| Validator | title, chapter content, outline/contract, handoff, accepted facts | Validator flow and validator memory budget | Fail closed when the structured response is invalid or missing `passed` |
| Extractor | completed content, outline, prior accepted state, character context | `run_post_processing` reloads `agent_type="extractor"` context | Candidate extraction is non-blocking unless a hard conflict is detected |

## Layered memory and authority

`services.novel_memory_recall.recall_novel_memory` reads doctrines, scene
blocks, accepted atoms, due foreshadowing atoms, and a bounded candidate set.
Role-specific atom and scene-type filters are applied before rendering. Accepted
items are rendered as usable facts; candidate items are rendered as explicitly
unconfirmed clues. Recall failures roll back the read transaction and return an
empty advisory result.

`services.chapter_continuity.build_chapter_handoff` is deterministic and does
not call a model. It combines the previous chapter ending with accepted state,
open questions, evidence boundaries, item state, and source metadata.

`services.continuity_contract.sanitize_outline_for_contract` deterministically
projects the Planner outline and handoff into a chapter contract. The same
contract is copied to Writer, Editor, and Validator flat fields.

## A1 compatibility boundary

`agents.context_bundle.AgentContextBundle` wraps these fields into bounded,
role-specific `ContextSection` objects with source, chapter, version, and
authority metadata. `PipelineContext.context_bundle` and
`get_context_bundle()` are available, while all flat fields remain for
compatibility. Current production prompts still read the flat fields through
the Agent classes. Therefore A1 changes the data contract and observability,
but does not yet constitute a full Prompt migration.

The intentionally empty legacy fields (`world_state`, `character_state`,
`foreshadowing`, and `plot_threads`) are not silently populated by A1. In the
layered path, canonical context comes from the four memory projections,
character manifests, handoff, contract, and advisory vector context.

## Ariadne-derived opportunity

The next additive projection is deterministic story events, story segments,
and stage summaries. These are navigation and continuity indexes, not a fifth
memory layer and not a replacement for character cards, Scene Blocks, atoms,
or evidence.
