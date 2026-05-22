# Web UI verification and visual evidence

## Baseline capture

- Date: 2026-05-22
- Worker: `worker-4`
- Scope: task 4 verification / visual evidence baseline before final implementation-lane handoff
- Runtime used:
  - frontend dev server on `http://127.0.0.1:5173`
  - backend API on `http://127.0.0.1:8000`
  - temp SQLite DB: `/tmp/worker4-web.sqlite3`
  - bootstrap account: `demo@example.com`
  - runner mode: `demo`

## Verification summary

- Typecheck: `cd frontend && npx tsc --noEmit -p tsconfig.json` → PASS
- Tests: `cd frontend && npm test` → PASS (`3` files, `51` tests)
- Lint: `cd frontend && npm run lint` → PASS
- Build: `cd frontend && npm run build` → PASS
- Full-stack browser smoke:
  - login screen rendered successfully
  - authenticated workspace rendered successfully with bootstrap demo account
  - screenshot inventory captured for all currently exposed workspace sections
- Direct API probe:
  - `GET /api/auth/oidc/status` → 200
  - `GET /api/governance/legal-holds?workspace_id=1` → 200
  - `GET /api/provisioning/events?workspace_id=1` → 200
  - `GET /api/stock-search?query=SPY` → 200
  - `POST /api/auth/register` with invalid short password → expected validation failure (`422`)

## Screenshot inventory

Stored under `docs/verification/web-ui-baseline/`:

| File | Bytes | Notes |
| --- | ---: | --- |
| `login.png` | 480801 | unauthenticated baseline |
| `analysis.png` | 375055 | authenticated analysis page |
| `history.png` | 419703 | authenticated history empty state |
| `memories.png` | 396320 | authenticated memory empty state |
| `schedules.png` | 369239 | authenticated schedules empty state |
| `interventions.png` | 416908 | authenticated intervention empty state |
| `governance.png` | 404237 | authenticated governance page |
| `compliance.png` | 363951 | authenticated compliance page |

## Observations

- The baseline authenticated shell is functional and exposes all seven workspace sections:
  - `股票分析`
  - `分析历史`
  - `智能体记忆`
  - `定时任务`
  - `人工介入`
  - `工作区治理`
  - `合规与身份`
- During browser navigation, Playwright observed a few non-200 frontend network responses tied to initial page activity. Direct API probes against the same temp backend returned `200` for the relevant endpoints, so the current evidence does **not** show a backend route regression.
- This is a baseline evidence pass only. Final acceptance still needs a post-implementation rerun, ideally with seeded UI states coordinated with `worker-2`.

## Pending final pass

Before task completion, rerun:

1. frontend typecheck / tests / lint / build on the final integrated branch state
2. authenticated visual capture after implementation lanes complete
3. any seeded-state screenshots supplied or enabled by `worker-2`

### Final rerun protocol

Wait until task 2 and task 3 are both complete, or until the leader explicitly confirms the integrated final branch state is ready.

Then rerun, in order:

```bash
cd frontend
npx tsc --noEmit -p tsconfig.json
npm test
npm run lint
npm run build
```

For final browser evidence, rerun against the leader-integrated code with:

- backend on `127.0.0.1:8000`
- frontend on `127.0.0.1:5173`
- temp bootstrap demo user
- any seeded/final UI states coordinated by `worker-2`

Required final evidence:

- fresh PASS/FAIL output for typecheck, tests, lint, and build
- refreshed screenshot inventory for:
  - login
  - analysis
  - history
  - memories
  - schedules
  - interventions
  - governance
  - compliance
- note any remaining non-200 browser/API responses and verify whether they reproduce through direct API probes before calling them regressions

### Current stop condition

Do **not** close task 4 using only the baseline evidence in this file. Baseline evidence is accepted only as an interim checkpoint; final completion requires a rerun on the post-integration UI state.

## Final integrated rerun

- Integrated tree verified on commit: `cf42242` (`Align App shell surfaces to the shared workstation token contract`)
- Final rerun date: 2026-05-22
- Execution context:
  - repo: `/home/ubuntu/git-project/TradingAgents`
  - frontend dev server: `http://127.0.0.1:5173`
  - backend API: `http://127.0.0.1:8000`
  - temp SQLite DB: `/tmp/worker4-web-final.sqlite3`
  - bootstrap user: `demo@example.com`
  - seeded one local demo analysis (`SPY`, `2026-05-01`) to exercise non-empty history / memory / flow UI

### Final verification results

- PASS typecheck: `cd frontend && npx tsc --noEmit -p tsconfig.json`
- PASS tests: `cd frontend && npm test` → `4` files, `53` tests
- PASS lint: `cd frontend && npm run lint`
- PASS build: `cd frontend && npm run build` → emitted:
  - `dist/assets/index-Oc4aZEMK.css`
  - `dist/assets/index-CiNTjM7Q.js`
- PASS seeded analysis smoke:
  - login succeeded
  - created analysis task `#1`
  - task completed via demo runner
  - post-run counts observed:
    - analyses: `1`
    - memories: `7`

### Final screenshot inventory

Stored under `docs/verification/web-ui-final/`:

| File | Bytes | Notes |
| --- | ---: | --- |
| `login-post-auth.png` | 426699 | authenticated shell after login |
| `analysis.png` | 426699 | analysis page with attached memories available |
| `history.png` | 421355 | history page with completed task card |
| `analysis-selected.png` | 751143 | selected completed analysis showing the real-time flow card |
| `memories.png` | 393040 | populated memory library |
| `memory-detail-modal.png` | 290898 | opened `MemoryDetailModal` with semantic chips + accent close button |
| `schedules.png` | 404997 | schedules page with memory-aware task form |
| `interventions.png` | 435844 | interventions empty state |
| `governance.png` | 437344 | governance page |
| `compliance.png` | 379529 | compliance / audit page with seeded audit history |

### Final browser/API findings

The integrated browser pass still observed these non-200 responses:

- `404 http://localhost:8000/api/auth/oidc/status`
- `403 http://localhost:8000/api/auth/register`
- `404 http://localhost:8000/api/governance/legal-holds?workspace_id=1`
- `404 http://localhost:8000/api/provisioning/events?workspace_id=1`
- `404 http://localhost:8000/api/stock-search?query=SPY`

Follow-up direct API probe against the same integrated backend reproduced:

- `POST /api/auth/login` → `200`
- `GET /api/auth/oidc/status` → `404`
- `GET /api/governance/legal-holds?workspace_id=1` → `404`
- `GET /api/provisioning/events?workspace_id=1` → `404`
- `GET /api/stock-search?query=SPY` → `404`

This means the final verification pass is complete, but it surfaced reproducible backend/API route mismatches or availability gaps on the integrated branch. Treat these as known findings from task 4 evidence, not just browser-only noise.

### Mandatory `.omx` screenshot artifact mirror

The plan-required local artifact folders were populated with exactly these six files in each folder:

- `.omx/artifacts/ui-optimization/screenshots/baseline/`
  - `login.png`
  - `workbench-idle.png`
  - `analysis-progress.png`
  - `report-reader.png`
  - `history.png`
  - `narrow-viewport.png`
- `.omx/artifacts/ui-optimization/screenshots/final/`
  - `login.png`
  - `workbench-idle.png`
  - `analysis-progress.png`
  - `report-reader.png`
  - `history.png`
  - `narrow-viewport.png`

These `.omx/` screenshots mirror the committed evidence under `docs/verification/` and are intentionally local runtime artifacts because `.omx/` is git-ignored.
