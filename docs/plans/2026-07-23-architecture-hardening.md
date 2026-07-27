# Architecture Hardening Implementation Plan

**Goal:** Reduce maintenance and reliability risks without breaking current contracts.

**Approach:** Extract frontend orchestration, split ORM declarations with compatibility re-exports, centralize persistence authority, harden atomic Worker claiming, and add focused regression tests.

**Scope:** Existing APIs, database tables, and user changes remain intact.
