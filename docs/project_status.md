# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P2 done. Next: **P3 auth, masters, ledger, seed**

**Live:** https://factoryflow-icdx.onrender.com (Render Free, Singapore, auto-deploys from `main`; Neon Free DB).
Verified 2026-11-23: `/api/v1/health` → `{"status":"ok","db":"ok"}`, `/` serves the placeholder page.
First deploy failed because Render's **Root Directory** was `docker/` (it must be empty); fixed in the dashboard.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | ✅ done |
| P2 | Core maths: money, units, gst, wac, variance (pure, unit-tested) | ✅ done |
| P3–P6 | Ledger → production → sales/invoice → payments (benchmark gate) | ⚪ P3 next |
| P7–P9 | PDF + reports → frontend + offline queue → README/design note/deploy | ⚪ |
| P10–P11 | Should-haves → stretch | ⚪ |

Full roadmap: [roadmap.md](roadmap.md). Interview prep per phase: [interview_notes.md](interview_notes.md).

## Decisions made
- Stack: FastAPI + SQLAlchemy 2 + Alembic + Postgres 16; React + Vite + Tailwind in **plain JS**; one deployable.
- Lot/expiry on every movement from day one. Allocation FIFO; FEFO is stretch.
- WAC per item, overheads per run ÷ good output, so cost/packet = ₹31.14 (spec B13).
- Hosting: Render Free web + Neon Free Postgres. No keep-alive pings.
- Minimal offline order queue in P8. Six seeded logins (spec §2).
- No MCP servers. `pyright-lsp` plugin: **only if it works with no extra setup, and only after the user approves.** It needs `npm i -g pyright`, so the default is to skip it.
- P1: sync SQLAlchemy (psycopg 3); settings via pydantic-settings; tests use a separate `factoryflow_test` DB
  rebuilt by Alembic. Benchmark request shapes in `test_section5.py` are the contract: a phase may adjust a
  path or payload when it builds the endpoint, **never an expected number**.
- API host port is `API_PORT` (default 8000) because another local project already uses 8000.
- P2: variance flag compares exact values (`|diff| × 10000 > tol × planned`), not the rounded bp.
  Receipt value is computed in the quoted unit before converting to base (per-gram rates aren't whole paise).

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- Render: Health Check Path is still empty; set it to `/api/v1/health` in the dashboard (optional, recommended).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).
- Benchmark test vs roadmap P3 "done when": the reconcile and orphan checks call `sc.require(9)` and RBAC
  `sc.require(4)`, so they can't pass in P3. Decided fix (P3): treat them as **invariants, not scenario
  checks**. (1) The scenario fixture runs reconcile + the orphan query after every completed step and records
  the result; the test asserts all were clean and at least one step posted movements. The same check runs as a
  teardown in `tests/integration/conftest.py` for any test that posts stock. (2) A route-policy test walks
  `app.routes` and fails if any `/api/v1` route lacks `require_roles(...)`, except a public allowlist
  (`/health`, `/auth/login`), plus a per-phase table of (role, method, path, status). The benchmark
  "salesman 403 on approve" check stays as is and turns green in P5.

## Benchmark scoreboard

`pytest -q`: 73 passed, 19 xfailed (2026-11-23). Every check currently stops at step 0 (`app.seed` not built).
The benchmark *arithmetic* (B8–B10, B12b, B13, A5) is already proven by unit tests in `tests/unit/`.

| Check | Status |
|---|---|
| B1–B13, B9b, B10b, B12b | ⏳ xfail |
| ledger reconciles · no orphan movements · salesman 403 on approve | ⏳ xfail |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
Start phase P3 on branch feat/p3-ledger, exactly as defined in docs/roadmap.md. It is the biggest phase
(~1.5 h): warn me if it may not fit, and split it into commits (auth, masters, ledger, audit, seed).
- auth: app_user + roles, PyJWT + bcrypt, POST /auth/login, require_roles() deny-by-default; the 6 logins
  from spec §2 (password = SEED_DEMO_PASSWORD).
- masters: item (+item_unit packs), stock_lot, BOM + lines, customer (GSTIN, state), supplier, price list,
  company settings (state 33). GET /items, /customers, /suppliers, /boms filterable by code (the shapes
  test_section5.py step 0 uses).
- inventory: stock_movement exactly as docs/architecture.md §3, append-only DB trigger (Alembic migration),
  post_movements() as the only writer (uses core.units / core.wac), balance(), reconcile(),
  GET /stock/balance/{item_id} → {"qty": "<decimal string>", "uom": "<base>"}.
- audit: audit_log + record(). Seed: `python -m app.seed` with `run()`, opening stock from PROBLEM §5.
Follow the stock-ledger skill. Rework reconcile/orphan/RBAC as invariants (see Open issues): check
reconcile + orphans after every scenario step and in an integration-test teardown, remove those two xfail
markers in the same commit once they pass; add the route-policy test (every /api/v1 route has
require_roles unless allowlisted) and a role table for P3's endpoints; the benchmark salesman-403 check stays
xfail (needs orders, P5). Add the append-only trigger test. Run the ledger-auditor only after P4.
Finish with tests and lint green, /update-docs-and-commit, merge to main, the teaching protocol, and an
updated next prompt for P4.
```
