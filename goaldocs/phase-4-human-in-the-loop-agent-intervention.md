# Phase 4 Goal: Human-in-the-Loop Agent Continuation and Intervention

## Objective

Build Phase 4 of the authenticated TradingAgents web platform: add auditable human-in-the-loop controls that let authenticated users pause, inspect, continue, and guide an individual agent's analysis path through explicit user messages, while preserving Phase 1 realtime/history, Phase 2 scheduling, Phase 3 memory attachment, and existing CLI behavior.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add SQLite schema/migration logic for intervention sessions, user messages, agent continuations, and audit events.
  - Add APIs to create, view, pause, resume, and close intervention sessions for a specific analysis task and agent.
  - Add APIs to append user guidance/messages to an intervention session.
  - Add a bounded continuation runner seam that can use selected prior task state, attached memories, and user guidance without corrupting the original analysis record.
  - Persist all intervention outputs as separate auditable events linked to the source analysis task.
- `frontend/`
  - Add agent-level intervention controls in analysis detail/realtime views.
  - Add an intervention chat/detail panel for a selected agent.
  - Show intervention timeline, user guidance, generated continuation output, status, and linked source task.
  - Make clear which outputs are original analysis versus human-guided continuation.
- `tests/`
  - Add auth/ownership tests for intervention APIs.
  - Add pause/resume/close lifecycle tests.
  - Add user-message persistence tests.
  - Add continuation-output persistence tests.
  - Add tests proving original Phase 1 analysis history remains immutable/auditable.
  - Add schedule/memory regression tests where relevant.
- `docs/web-ui.md`
  - Document human-in-the-loop workflow, audit model, limitations, and safety cautions.

## Non-goals

This phase does not include:

- Live mutation of an already-running LangGraph node unless a safe explicit seam already exists.
- Rewriting the core TradingAgents graph execution order.
- Multi-user collaborative intervention in the same session.
- Autonomous trading, broker integration, order placement, or fund management.
- Production-grade compliance approval workflows.
- Voice/video chat, file uploads, or rich document annotation.
- External queues, Redis, Celery, Postgres, vector databases, or external workflow engines unless explicitly approved.
- Breaking existing CLI behavior.

## Acceptance Criteria

- Authenticated users can start an intervention session from an existing analysis task and selected agent.
- Users can only access intervention sessions for their own analysis tasks.
- Each intervention session persists at minimum:
  - owner user id
  - source analysis task id
  - target agent name
  - status: `open`, `paused`, `closed`, `failed`
  - created timestamp
  - updated timestamp
  - closed timestamp when applicable
- Users can append guidance/messages to an open intervention session.
- User messages persist with author, content, timestamp, and sequence/order.
- Users can pause, resume, and close an intervention session.
- Users can trigger a continuation run for the target agent using:
  - original analysis context available from the source task
  - selected attached memories when applicable
  - explicit user guidance from the intervention session
- Continuation outputs persist separately from original analysis report sections.
- Analysis detail/history shows linked intervention sessions without overwriting the original final decision/report.
- Realtime UI displays intervention progress/events when a continuation is running.
- Original Phase 1 analysis event log and report remain auditable and distinguishable from human-guided continuation outputs.
- Phase 2 schedules continue to create normal analyses unaffected by intervention sessions.
- Phase 3 memory selection/attachment continues to work and can be used as context for intervention continuations.
- Existing CLI commands continue to work.
- New backend behavior has focused tests.

## Validation

Run backend tests:

```bash
python3 -m pytest -q
```

Run frontend validation:

```bash
cd frontend
npm install
npm run build
npm test
npm run lint
```

Run changed-scope lint:

```bash
ruff check tradingagents/web tests/test_web_backend.py frontend
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run Web intervention smoke checks:

- Unauthenticated intervention API request returns 401 or 403.
- Authenticated user can create an analysis task.
- Authenticated user can create an intervention session for a specific agent on that task.
- Another user cannot access that intervention session.
- User can append guidance messages.
- User can pause, resume, and close a session.
- User can trigger a continuation run and see persisted continuation events/output.
- Source analysis detail shows linked intervention sessions.
- Original analysis report/final decision remains unchanged.
- SQLite contains intervention session, message, event, and continuation output records.

## Stop Conditions

Stop and ask the user if:

- Implementing true mid-node live graph mutation is required instead of a separate auditable continuation session.
- The change requires substantial core graph execution-order redesign.
- Intervention context could expose another user's task, memories, or messages.
- Continuation semantics require external workflow infrastructure or distributed locking.
- The desired UI requires file uploads, voice/video, collaborative editing, or production compliance approval flows.
- Context size limits cannot be enforced safely.
- Existing Phase 1 realtime/history, Phase 2 scheduling, Phase 3 memory attachment, or CLI behavior would need to be broken.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash.
- Major files added or changed.
- SQLite schema/table summary for intervention sessions, messages, events, and continuation outputs.
- API route list for intervention operations.
- Frontend intervention UI summary.
- Agent continuation design and how it separates original analysis from human-guided output.
- Context construction rules, including memory use and length limits.
- Test, lint, build, and smoke results.
- Known risks and recommended Phase 5 follow-up.

## Suggested Phase 5 Follow-up

Production hardening: deployment guide, HTTPS/reverse proxy assumptions, stronger registration/admin provisioning, rate limiting, audit exports, retention/delete workflows, backup/migration strategy, and broader security review for internet-facing use.
