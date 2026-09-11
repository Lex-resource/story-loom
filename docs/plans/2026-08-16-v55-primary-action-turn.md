# V55 Primary Action Turn

## Goal

Reduce procedural query loops and improve character/writing scores without
adding a model call or weakening V53's cross-chapter stage boundary.

## Observation from A40/V54

V54's bounded `unique_action_ledger` prevented the known duplicate-operation
class in the completed chapter, but the chapter still read as query,
confirmation, and explanation. Character portrayal and writing quality were
both `8/10`. A40 was paused after chapter 2 and is excluded from ranking.

## Controlled change

V55 adds a compact `primary_action` to the shared chapter contract. It has
five fields: `action`, `response`, `decision`, `cost_or_risk`, and
`new_stage`. Planner must produce one core turn. Writer must realize one
action, one observable response, and one character decision or cost. Editor
compresses additional query/confirmation loops. Validator treats missing
decision texture as a warning, while hard fact, timeline, location,
character-state, and core-event conflicts retain the existing retry policy.
Extractor persists only the realized turn.

The V54 field remains accepted for compatibility, but V55's prompt surface
does not use the action ledger as the primary narrative driver. No database
field, memory layer, frontend page, or default model call is added.

## Runtime controls

Use a fresh project from the fixed published chapter-1 seed, a new layered
memory namespace, OpenAI / `gpt-5.6-luna` only, backup disabled, hybrid recall
disabled, `chroma_local` embeddings, and `bootstrap_skeleton=false`. Generate
chapters 2-10 and record all prompts, responses, provider metadata, quality
dimensions, wall-clock time, token counts, memory context, and retry classes.

## Acceptance

The run is eligible only if it completes all nine generated chapters, has no
hard setting/character/timeline conflicts, average content retries at most
one, at least 80% retry-free chapters, and reaches the existing seven-
dimension quality gates. A partial run is preserved and excluded.
