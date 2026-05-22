# Web Analysis Platform Phase 1 Design

## Design basis
`goaldocs/goal.md` is the approved product specification for Phase 1. This design keeps scope to authenticated single-stock analysis, deterministic SQLite persistence, realtime event delivery, history/rerun, and a Vite React UI. It explicitly defers scheduling, per-agent memory selection, full human takeover, external queues, external databases, OAuth/RBAC, broker integrations, and portfolio workflows.

## Architecture
The backend is a new `tradingagents.web` package exposing a FastAPI app factory. SQLite is the only persistence layer and stores users, bearer sessions, analysis tasks, normalized task parameters, agent event logs, report sections, and final decisions. The web runner has a narrow callback contract so the existing graph/CLI path remains unchanged while web tasks can persist event/status updates.

## Frontend
The frontend is a separate `frontend/` Vite React TypeScript application styled with Tailwind and local shadcn-style primitives. It includes login/logout, analysis configuration, realtime event stream, final report/decision display, history list/detail, and rerun controls.

## Testing
Backend tests use temp SQLite files and the deterministic demo runner to avoid LLM/network calls. Frontend validation is build/test/lint capable once dependencies are installed with npm.
