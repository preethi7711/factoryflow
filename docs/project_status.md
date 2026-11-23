# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P4 done (ledger-audited). Next: **P5 orders, invoice, dispatch**

**Live:** https://factoryflow-icdx.onrender.com (Render Free, Singapore, auto-deploys from `main`; Neon Free DB).
Verified 2026-11-23 (P3): `/api/v1/health` → `{"status":"ok","db":"ok"}`, `/` serves the placeholder page,
P3 migration applied on Neon. First deploy failed because Render's **Root Directory** was `docker/`; fixed.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | ✅ done |
| P2 | Core maths: money, units, gst, wac, variance (pure, unit-tested) | ✅ done |
| P3 | Auth/RBAC, masters, append-only ledger, audit, seed | ✅ done |
| P4 | Purchases + production runs, variance, overheads, cost; ledger-audited | ✅ done |
| P5–P6 | Sales/invoice → payments (benchmark gate) | ⚪ P5 next |
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
- P4: actual consumption/output are **read from the ledger** (ISSUE/OUTPUT movements), never stored twice,
  so `/variance` and `/cost` can't diverge from stock. Overheads are value-only COST_ADJUST on the FG lot.
- P4 (after the ledger-auditor): posted documents are append-only at the DB (`purchase`/`run`/lot/adjustment/
  overhead can't be deleted; a run is frozen once COMPLETED). `post_movements()` reads balances as of the
  movement date (no backdated overdraw), refuses an unknown source document, rounds once per issue line, and
  locks items before inserting referencing rows (concurrent posts → 409, not a deadlock). pcs/pkt are whole;
  BOMs are admin-only. 56-test audit suite in `tests/audit/` is the regression guard.

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- After pushing P4, confirm the Render deploy is live and the two new migrations applied on Neon.
- Render: Health Check Path is still empty; set it to `/api/v1/health` in the dashboard (optional, recommended).
- Live DB: migrations run on every deploy, but Neon is **not seeded**, so the live site has no logins yet.
  Decide by P8: run `python -m app.seed` against Neon from a local shell, or seed at startup behind an env flag.
- **B13 benchmark check stays xfail until P6:** it calls `sc.require(8)` (overheads), which comes after orders
  (P5) and payment (P6). ₹31.14 is already proven by `tests/integration/test_production.py::test_b13_*`.
  Remove the B13 xfail marker in the commit that makes scenario step 8 reachable (P6).
- WIP gap (no test): materials issued to a run that never completes have left stock and show in no report
  (no work-in-progress account, no run reversal yet). Revisit with reversals in P5.
- Not built yet: REVERSAL movements and credit notes (P5); order idempotency (P5/P8); edit/deactivate
  endpoints for masters (create only so far).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 215 passed, 8 xfailed (2026-11-23). That is 159 (P1–P3) + 56 ledger-audit tests. The scenario
now runs through step 3 (purchase, run, output) and stops at step 4 (`POST /orders`, P5).

| Check | Status |
|---|---|
| Ledger reconciles / no orphans after every step | ✅ pass |
| B1–B6 (closing balances, FG after run) | ✅ pass |
| B8, B9, B9b (yield and consumption variance) | ✅ pass |
| B13 cost per packet ₹31.14 | ✅ proven in `test_production.py`; benchmark check xfail until P6 |
| B7, B10, B10b, B11, B12, B12b | ⏳ xfail (orders/invoice/payment: P5, P6) |
| Salesman 403 on approve | ⏳ xfail (needs orders, P5) |
| ledger-auditor P4 | ✅ books trustworthy (56/56 green) |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
Start phase P5 on branch feat/p5-sales, exactly as defined in docs/roadmap.md (~1.5 h; warn me if it may not
fit; commit per module). Follow the stock-ledger and gst-rules skills; post stock only via post_movements().
Match the request/response shapes in tests/benchmark/test_section5.py steps 4-6 (don't change expected numbers).
- sales: sales_order (+ order_line), client_uuid UNIQUE, idempotent create via the Idempotency-Key header
  (same key + same body -> replay stored response; same key + different body -> 409). Server re-prices from
  the price list. POST /orders (salesman; a salesman sees/creates only their own customers' orders, 403 on
  others). Approval with a stock-cover check: available = FG on hand - approved-but-undispatched; over-approval
  -> 409 INSUFFICIENT_STOCK with requested/available/shortage (B12: shortage 32). POST /orders/{id}/approve
  (admin; salesman 403 -> turns the benchmark salesman-403 check green). GET /orders/{id}/tax-preview (B12b:
  INTER, IGST 300, total 6300).
- billing: invoice from an approved order, FY numbering FF/2026-27/0001 gapless via a row-locked sequence,
  per-line CGST+SGST or IGST by place of supply (B10: 7500 + 187.5 + 187.5 = 7875; B10b number). Dispatch
  posts DISPATCH movements (B7: FG 238 -> 88). POST /orders/{id}/invoice, POST /invoices/{id}/dispatch (admin).
Remove the xfail markers of B7, B10, B10b, B12, B12b and salesman-403 in the commit that makes them pass.
Then run the ledger-auditor subagent (attacks 4, 8, 9 are now in scope: idempotency replay, reversal
symmetry, invoice numbering) and fix what it confirms. B11 and the full green come in P6 (payments).
Finish with tests and lint green, /update-docs-and-commit, merge to main, the teaching protocol, and an
updated next prompt for P6.
```
