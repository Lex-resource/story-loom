# Design Options

## Option A: Context-only adaptation

`AgentContextBundle` is a deterministic projection around existing context.
It has no tables, no extra model calls, and preserves the flat compatibility
adapter. This is the lowest-risk first step and is implemented as A1.

## Option B: Context plus narrative projections

Add deterministic story-event, story-segment, and stage-summary indexes derived
from the chapter outline, handoff, contract, extractor output, and accepted
memory. These records answer “what happened where and when” without duplicating
the four memory layers. They can improve targeted recall and foreshadowing
tracking without a per-chapter summary call. This is the selected A2 path.

## Option C: Full workflow adoption

Importing Ariadne-style Detail, Critic, Prudent, and Polisher nodes as default
workflow stages would add calls, latency, and more failure surfaces. They are
kept as a gated future experiment. The V12 production baseline remains the
reference until an independent quality and retry comparison justifies a
change.

## Selection rule

Progress from A1 to A2 only if deterministic projections can be made
idempotent, source-linked, and bounded. Progress from A2 to A3 only after the
projection tests pass and a real single-chapter run shows no increase in
default model calls. No Ariadne implementation or licensed resource is copied
into the product repository.
