# V52 Visible Consequence Chain

## Decision

Skip the unfinished A37/V51 runtime sample and start A38/V52 from the same
published chapter-1 seed. Keep V51's character-agency prompt as the parent
surface, but replace a vague "make one choice visible" instruction with a
bounded observable chain: explicit action, scene response, and visible change.

## Evidence from V51

The first clean V51 chapter scored `8.71/10`, but required one Writer content
retry. The Validator's warning identified the remaining failure precisely:
Lin Mo's choice to continue investigating was rendered as waiting and staring,
and the Planner contract had an empty `dramatic_turn.choice`. The chapter also
repeated the same interface-state explanation. V51 is therefore retained as a
valid prompt experiment but skipped for the ten-chapter comparison.

## Controlled change

- Planner must fill `dramatic_turn.choice` with one finite, observable action.
- The action must produce a response from an already established device,
  location, character, or fact.
- The response must visibly change action, position, time cost, exposure risk,
  or investigation strategy.
- Writer may not treat waiting, staring, repeated clicking, repeated questions,
  or psychological summary as a choice or consequence.
- Editor removes procedural repetition and preserves the shortest action to
  consequence chain.
- Validator reports an incomplete soft chain as a warning only; hard authority,
  timeline, location, item, character-state, and core-event conflicts remain
  blocking.
- Extractor stores only explicit actions, observed responses, and visible
  changes.

No new model call, database field, memory layer, or frontend surface is added.
V50 evidence repair and V51 character-agency rules remain inherited.

## Runtime gate

The clean A38 project must contain only the fixed published chapter 1, initial
character state, and a fresh layered-memory namespace. The first rendered
Planner, Writer, Editor review/destyle/force-revise, Validator, Extractor
summarize/extract, and character-card extraction prompts must contain both
`V52 可见后果链` and the inherited `V51 角色选择落地` marker where the branch
is rendered. OpenAI remains the sole provider; backup and hybrid retrieval stay
disabled.

## Acceptance

Run up to ten chapters from chapter 2. Record every prompt and response,
quality dimension, retry type, token count, memory-context size, and wall-clock
time. Stop the sample on a hard conflict or if the first two chapters fall
below `8.3/10`; preserve all raw artifacts. The candidate must still meet the
project gates: seven-dimensional average at least `8.5`, continuity and
foreshadowing at least `8.5`, no hard conflicts, average content retries at
most one, and at least 80% zero-content-retry chapters.

