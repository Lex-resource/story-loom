# V58 Structured Character Turn

## Goal

Repair the V57 failure where the compact prompt removed procedural pressure but
the Planner omitted the shared turn fields, leaving Writer without a concrete
character choice.

## Controlled change

V58 keeps V57's compact role-specific prompt surface but makes
`primary_action` and `character_turn` required, non-empty Planner outputs with
fixed fields. The deterministic contract fills only missing character-turn
fields from the already supplied `character_goals` and `primary_action`; it
does not invent a motive, fact, entity, or model call. All five Agents use the
same normalized projection.

## Runtime controls

Use a fresh fixed chapter-1 seed, a new layered-memory namespace, OpenAI /
`gpt-5.6-luna` only, backup disabled, hybrid recall disabled, and local Chroma
embeddings. Generate chapters 2-10 and preserve all prompts, responses,
quality scores, retries, tokens, memory snapshots, and wall-clock metrics.

## Hypothesis

The Planner must provide a usable, source-bounded turn before prompt
compression can improve prose. V58 should retain V57's lower prompt burden and
restore a visible choice/cost chain without increasing default model calls.
