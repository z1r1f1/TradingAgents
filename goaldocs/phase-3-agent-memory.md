# Phase 3 Goal: Per-Agent Analysis Memory and Selectable Knowledge Attachment

## Objective

Build Phase 3 of the authenticated TradingAgents web platform: add SQLite-backed per-agent historical stock-analysis memory so authenticated users can browse, search, select, and attach prior agent memories as additional context for new manual or scheduled analyses, while preserving Phase 1 history/realtime behavior, Phase 2 scheduling, and existing CLI behavior.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add SQLite schema/migration logic for per-agent memories and analysis-memory attachments.
  - Extract agent memories from completed analysis events and report sections.
  - Add APIs to list, search, view, tag, archive, and attach memories.
  - Integrate selected memories into web analysis task creation and scheduled execution.
  - Keep the existing core graph behavior unless a narrow context-injection seam is needed.
- `frontend/`
  - Add memory browser/search UI.
  - Add per-agent memory detail UI.
  - Add memory selection controls in manual analysis configuration.
  - Add memory selection controls in schedule create/edit forms.
  - Show which memories were attached to a completed analysis.
- `tests/`
  - Add memory extraction, ownership, search/filter, archive, attachment, and schedule-integration tests.
- `docs/web-ui.md`
  - Document memory storage, selection workflow, context-injection behavior, limitations, and privacy/security cautions.

## Non-goals

This phase does not include:

- Vector databases, external embedding services, Redis, Postgres, or object storage.
- Automatic semantic retrieval unless it can be implemented locally and simply with SQLite/text search.
- Cross-user memory sharing.
- Human-in-the-loop mid-run intervention.
- Multi-stock portfolio-level analysis.
- Production-grade knowledge governance, retention policies, or compliance workflows.
- Broker integration, real trading, order placement, or fund management.
- Breaking existing CLI behavior.

## Acceptance Criteria

- Completed analyses produce per-agent memory records for relevant agent outputs, at minimum:
  - Market Analyst
  - Social Analyst when selected
  - News Analyst when selected
  - Fundamentals Analyst when selected
  - Research Manager
  - Trader
  - Portfolio Manager
- Each memory record persists at minimum:
  - owner user id
  - source analysis task id
  - ticker
  - analysis date
  - agent name
  - memory title or summary
  - memory content
  - tags or metadata JSON
  - created timestamp
  - archived flag/status
- Users can only access their own memories.
- Users can list and filter memories by ticker, agent, date, text query, and archived status.
- Users can view a single memory detail record.
- Users can archive/unarchive memory records.
- Manual analysis creation supports selected memory ids.
- Schedule creation/edit supports selected memory ids to attach on each execution.
- Attached memories are persisted per generated analysis task.
- Analysis detail/history shows which memories were attached.
- Selected memories are injected into the web analysis context in a deterministic, bounded way.
- Context injection has length limits and does not silently exceed configured bounds.
- Phase 1 realtime/history behavior continues to work.
- Phase 2 schedules and manual triggers continue to work.
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

Run Web memory smoke checks:

- Unauthenticated memory API request returns 401 or 403.
- Authenticated user can create an analysis and memory records are extracted after completion.
- Authenticated user can list/search/filter memory records.
- Authenticated user can archive and unarchive a memory.
- Authenticated user can launch a new analysis with selected memory ids.
- Analysis detail shows attached memories.
- Schedule manual trigger can attach its configured memories to the generated analysis task.
- SQLite contains memory and analysis-memory attachment records.

## Stop Conditions

Stop and ask the user if:

- The implementation appears to require vector DBs, embedding APIs, Redis, Postgres, or external infrastructure.
- Memory context injection requires substantial core graph execution-order changes.
- Memory records may expose one user's data to another user.
- The desired retrieval behavior requires semantic search rather than explicit user selection or simple local text search.
- Context size limits cannot be enforced safely.
- Existing Phase 1 auth/history/realtime behavior or Phase 2 scheduling would need to be substantially redesigned.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash.
- Major files added or changed.
- SQLite schema/table summary for agent memories and memory attachments.
- API route list for memory operations.
- Frontend memory UI summary.
- Memory extraction rules by agent/report section.
- Memory attachment and context-injection design, including length limits.
- How scheduled analyses attach selected memories.
- Test, lint, build, and smoke results.
- Known risks and recommended Phase 4 follow-up.

## Suggested Phase 4 Follow-up

Add human-in-the-loop continuation and agent-specific dialogue intervention so users can pause or continue an individual agent's analysis path with explicit user guidance while preserving auditability and realtime event history.
