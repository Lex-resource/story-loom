# Reliability and Design Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the fifteen identified architecture, concurrency, security, observability, frontend boundary, and test coverage issues while preserving existing APIs.

**Architecture:** PostgreSQL becomes the coordination authority for commands and active work. API endpoints become the sole mutation path, workers atomically claim durable work, projections remain rebuildable, and frontend code uses domain API clients rather than raw fetch calls.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, PostgreSQL, Alembic, React, Zustand, Vite, pytest.

---

1. Add database invariants, indexes, and durable intervention fields.
2. Centralize pipeline commands and remove WebSocket mutations.
3. Atomically claim vector outbox rows across workers.
4. Add settings redaction, local access enforcement, and remove secret query APIs.
5. Add storage reconciliation health and operational logging.
6. Remove service-to-worker reverse dependencies and clarify config ownership.
7. Introduce frontend domain API clients and reduce controller parameter coupling.
8. Restore focused state-machine, concurrency, security, and route tests.
