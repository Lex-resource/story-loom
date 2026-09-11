# V48 Memory Merge Implementation Plan

**Goal:** Prevent generated observational world-rule updates from being misclassified as hard conflicts while preserving authority and hard-marker protection.

**Architecture:** Keep conflict decisions deterministic in `services/novel_memory_atoms.py`. A generated `merge` may supersede a generated accepted atom when its payload contains an allow-listed observation field; protected authorities, explicit replacement without evidence, and changed hard markers remain blocking. V48 changes no model prompt, database schema, memory budget, or call count.

**Tech Stack:** Python, SQLAlchemy models, pytest, CodeGraph, local experiment recorder.

---

## Context

A33/V47 chapter 3 produced two generated `world_rule` merge candidates for `B-17历史回执` and `白塔入口设备`. The candidates only added observed display and response state (`visible_structure`, `layout`, `adjacent_element`, `current_status`, and `response_scope`), but the merge allow-list did not recognize those fields. The chapter was therefore paused even though Validator quality was `8.71/10` and the chapter had no content, API, or JSON retry.

## Tasks

1. Add the observed display/layout/status fields to the world-rule observation allow-list.
2. Keep `_stable_field_conflict` unchanged so `rule_type`, `confirmed`, `frozen`, and `locked` changes still block.
3. Add a regression test using the exact A33 extractor payload shape.
4. Add a regression test proving a changed hard marker is still blocked.
5. Extend experiment version recognition through V48.
6. Run targeted tests, full tests, CodeGraph sync, and a clean V48 Prompt gate before starting A34.

## Evaluation

The implementation is accepted only if the A33-shaped merge is promoted, hard-marker changes remain blocked, all existing memory conflict tests pass, and the first V48 Prompt snapshots are recorded under a new run directory. A34 remains excluded if its Worker starts with stale code or if the prompt/version gate fails.
