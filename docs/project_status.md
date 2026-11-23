# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P3 done. Next: **P4 purchase + production run**

**Live:** https://factoryflow-icdx.onrender.com (Render Free, Singapore, auto-deploys from `main`; Neon Free DB).
Verified 2026-11-23 (P2): `/api/v1/health` → `{"status":"ok","db":"ok"}`, `/` serves the placeholder page.
First deploy failed because Render's **Root Directory** was `docker/` (it must be empty); fixed in the dashboard.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | ✅ done |
| P2 | Core maths: money, units, gst, wac, variance (pure, unit-tested) | ✅ done |
| P3 | Auth/RBAC, masters, append-only ledger, audit, seed | ✅ done |
| P4–P6 | Production → sales/invoice → payments (benchmark gate) | ⚪ P4 next |
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
- P3: reconcile, API balance = SUM(ledger) and no-orphans are **invariants**, checked after every completed
  benchmark step and as a teardown after every integration test (`tests/invariants.py`). A route-policy test
  fails if any route lacks `require_roles(...)` (allowlist: `/health`, `/auth/login`).
- P3: `post_movements()` is the only ledger writer. It locks item rows in id order, allocates FIFO lots for an
  outflow that names none, values outflows at WAC and refuses COST_ADJUST on zero stock. It never commits;
  the calling service commits the document, movements and audit row together.
- P3: the token carries only the user id; role and active flag are re-read from the DB on every request.
- P3: opening stock is a `stock_adjustment` document (kind OPENING), dated 31 Oct 2026 (A17).
- P3: production refuses to start with a weak `JWT_SECRET_KEY` (< 32 chars or the dev default).

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- Render: after pushing P3, confirm the deploy is live. If it fails with "JWT_SECRET_KEY must be a random value
  of 32+ characters", set a new key in the Render dashboard (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- Render: Health Check Path is still empty; set it to `/api/v1/health` in the dashboard (optional, recommended).
- Live DB: migrations run on every deploy, but Neon is **not seeded**, so the live site has no logins yet.
  Decide by P8: run `python -m app.seed` against Neon from a local shell, or seed at startup behind an env flag.
- **B13 vs roadmap P4 "done when":** `test_b13` calls `sc.require(8)`, and step 8 (overheads) comes after
  orders (P5) and payment (P6), so the benchmark B13 can't pass in P4. Proposed: P4 proves ₹31.14 with its own
  integration test (purchase → run → overheads → cost), and the benchmark B13 turns green in P6. Confirm.
- Not built yet: REVERSAL movements (credit notes, P5); a concurrency test for "no negative stock" (ask the
  ledger-auditor after P4); edit/deactivate endpoints for masters (create only so far).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 126 passed, 17 xfailed (2026-11-23). The scenario now completes step 0 (seed, logins, lookups)
and stops at step 1 (`POST /purchases`, P4). The arithmetic of B8–B10, B12b, B13 and A5 is proven by unit tests.

| Check | Status |
|---|---|
| Ledger reconciles after every step | ✅ pass |
| No orphan movements after any step | ✅ pass |
| B1–B13, B9b, B10b, B12b | ⏳ xfail |
| Salesman 403 on approve | ⏳ xfail (needs orders, P5) |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
Start phase P4 on branch feat/p4-production, exactly as defined in docs/roadmap.md (~1.5 h; warn me if it
may not fit; commit per module). Follow the stock-ledger skill; post stock only via post_movements().
- purchasing: purchase + purchase_line (supplier, date, item, qty in any unit of its dimension,
  rate_paise per that unit, tax-exclusive, input GST recorded but not costed: A15). Each line creates a lot
  and posts PURCHASE at receipt_value. POST /purchases (role production), as test_section5.py step 1 sends it.
- production: production_run (BOM, batches, run_date, DRAFT -> COMPLETED) + run_consumption (planned vs
  actual per BOM line) + run_overhead. POST /production-runs issues the raw materials (step 2);
  POST /production-runs/{id}/complete issues packaging (pouches 194 incl. 6 damaged, recorded as damaged_qty),
  creates FG lot RUN-0001 (expiry = run date + shelf life, A16) and posts OUTPUT +188 at material cost
  (step 3); GET .../variance (B8, B9, B9b; A1–A4); POST .../overheads posts COST_ADJUST on the run's FG lot
  (A14) and GET .../cost returns material, overhead, total, good_qty, cost_per_unit_paise (step 8 shapes).
  Audit-log run creation, completion and overheads. Roles: production (admin may read).
Remove the xfail markers of B1–B6, B8, B9, B9b in the same commit as the code that makes them pass.
B13 needs scenario step 8 (after P5/P6): prove Rs 31.14 with P4's own integration test and leave the
benchmark B13 xfail (see Open issues). Then run the ledger-auditor subagent and fix what it confirms.
Finish with tests and lint green, /update-docs-and-commit, merge to main, the teaching protocol, and an
updated next prompt for P5.
```
