# Web Analysis Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 of an authenticated FastAPI/SQLite + React web platform for single-stock TradingAgents analysis.

**Architecture:** Add `tradingagents.web` with settings, SQLite repository, auth/session handling, task runner, and FastAPI routes. Add `frontend/` Vite React TypeScript UI with Tailwind/shadcn-style components. Preserve CLI by wrapping the existing graph from new web code instead of changing CLI execution.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, Pydantic, pytest, React, Vite, TypeScript, Tailwind CSS.

---

### Task 1: Backend tests and schemas
- [x] Write failing pytest coverage in `tests/test_web_backend.py` for auth, protected routes, SQLite task persistence, history/rerun, and SSE event output.
- [x] Verify RED before production code.

### Task 2: SQLite/auth/API backend
- [x] Create `tradingagents/web/settings.py`, `database.py`, `auth.py`, `schemas.py`, `runner.py`, `service.py`, and `main.py`.
- [x] Implement deterministic demo runner plus real graph-runner extension point.
- [x] Verify targeted backend tests pass.

### Task 3: Frontend
- [x] Create `frontend/` Vite React TypeScript project with Tailwind config and shadcn-style primitives.
- [x] Implement login/logout, analysis form, realtime event display, final report, history detail, and rerun.

### Task 4: Documentation and verification
- [x] Add `docs/web-ui.md` with setup, run, limitations, routes, SQLite tables, and extension points.
- [ ] Run `pytest`, frontend install/build/test/lint where available, CLI/web smoke checks, and audit acceptance criteria.
