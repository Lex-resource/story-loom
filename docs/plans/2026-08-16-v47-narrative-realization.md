# V47 Narrative Realization Implementation Plan

## Goal

V46 made the goal-pressure-choice-consequence structure visible to every
writing Agent, but the first seven chapters still read as repeated interface
queries and evidence explanations. Character portrayal and writing quality
remain around 7-8, while soft wording mismatches continue to cause content
retries. V47 tests whether the missing quality is a rendering problem rather
than a missing memory field.

## Controlled change

V47 keeps V46 unchanged as the parent behavior:

- OpenAI-only provider, backup disabled, and `chroma_local` embeddings.
- The same four-layer memory, accepted-fact authority boundary, candidate and
  unknown handling, compact context budgets, artifact boundary, and no
  Polisher configuration.
- No database field, memory layer, or model call is added.

The only new behavior is a compact role-specific prompt hint. Planner supplies
concrete action anchors without inventing traits. Writer treats `dramatic_turn`
as a backstage route and renders each important change through a bounded
visible action, pause, sensory load, or relationship response. Editor performs
local prose compression. Validator treats sparse characterization, repetition,
and style as warnings rather than retryable hard failures. Extractor stores only
observed actions and state changes, never inferred personality or motive.

## Hypothesis

If V46's structure is kept but no longer explained in prose, character and
writing scores should improve without increasing the content retry rate. A
failure would indicate that the seed character state or chapter premise is the
limiting factor, rather than prompt realization.

## Verification

- `tests/test_v47_narrative_realization.py`
- V46, V45, and V44 regression tests
- full Python test suite and `compileall`
- CodeGraph sync and impact check
- fresh A33 project from the fixed published chapter-1 seed
- OpenAI-only startup gate for V47 markers in Planner, Writer, Editor,
  Validator, and Extractor snapshots

## Experiment

- Prompt version: `V47`
- Variant: `ariadne-A33-v47-narrative-realization-no-polisher`
- Ten generated chapters, starting at chapter 2 after the fixed chapter-1 seed
- No shared A32 body, layered memory, or manually edited正文
- Preserve every rendered prompt, response, event, metric, and quality score
