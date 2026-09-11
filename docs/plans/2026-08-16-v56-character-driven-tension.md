# V56 Character-Driven Tension

## Goal

Improve character portrayal and writing quality without increasing model calls
or weakening V55's cross-chapter and authority boundaries.

## Observation from A41/V55

V55 made the external action chain cleaner and kept content retries at zero in
the completed sample, but the fixed seed's empty static character card left the
result procedural. `primary_action` described what happened, but it did not
give Writer a compact, source-bounded answer for why this character made that
choice under current pressure.

## Controlled change

V56 adds a deterministic `character_turn` projection with `actor`, `goal`,
`pressure`, `choice_basis`, `choice`, `personal_cost`, and `state_change`.
Planner produces it from character-card facts, accepted prior state, and
visible chapter pressure. Writer, Editor, Validator, and Extractor receive the
same projection. Empty character-card fields remain empty; the model is
forbidden from inventing personality, background, relationships, abilities, or
motives. Technical actions remain a single `primary_action` and are rendered
as a short carrier for the character turn.

No new database table, memory layer, frontend surface, or default model call is
added. V55 remains backward-compatible for saved outlines without the field.

## Runtime controls

Use a fresh project from the fixed published chapter-1 seed, a new layered
memory namespace, OpenAI / `gpt-5.6-luna` only, backup disabled, hybrid recall
disabled, `chroma_local` embeddings, and `bootstrap_skeleton=false`. Generate
chapters 2-10 and record all prompts, responses, memory snapshots, quality
dimensions, retry classes, tokens, and wall-clock metrics under
`data/research_runs/`.

## Acceptance

The run is eligible only if all nine generated chapters complete, there are no
hard setting/character/timeline conflicts, average content retries are at most
one, at least 80% of chapters have zero content retries, and the existing
seven-dimensional quality gates are met. V56 is specifically compared against
V55 on character portrayal, writing quality, and procedural repetition.
