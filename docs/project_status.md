# Project status (session handoff file)

_Last updated: 2026-11-24_

## Current phase: P7 done — reports + invoice PDF (ledger-audited). Next: **P8 frontend + offline order queue**

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
| P5 | Orders (idempotent) → approve + stock check → invoice (GST, FY no.) → dispatch + credit notes; ledger-audited | ✅ done |
| P6 | Payments + allocation + outstanding — **benchmark gate GREEN**; ledger-audited | ✅ done |
| P7 | Invoice PDF + reports (registers, stock, production) + CSV/XLSX export; ledger-audited | ✅ done |
| P8 | Frontend (thin): login, salesman mobile order + offline queue, admin/production/stock screens | ⚪ next |
| P9 | README + design note + final deploy check + demo-video script | ⚪ |
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
- P5: orders are priced server-side from the price list; the `Idempotency-Key` is the order's UNIQUE
  `client_uuid` and is also stored (with the request hash and the stored response) in `idempotency_key`,
  so a replay returns the first order and a different body under the same key is 409. Approval reserves FG
  **logically** (available = on hand − approved-but-undispatched); no stock moves until dispatch.
- P5: invoice numbering is gapless per FY via a `FOR UPDATE` row on `invoice_sequence` (a rolled-back
  invoice un-bumps it). A posted invoice is never deleted; `POST /invoices/{id}/cancel` writes a credit
  note and `inventory.post_reversals()` mirrors the dispatch (same lot, opposite qty/value, `reverses_id`
  UNIQUE), so cancelling restores stock and WAC exactly.
- P5 (after the ledger-auditor): an outflow checks the **current** per-lot balance as well as the
  as-of-date one, so a backdated out-of-order dispatch can't drive a lot negative; the idempotency
  double-tap replays for the loser (guard wraps the flush); replay is scoped to the key's owner.
  17-test P5 audit suite in `tests/audit/` guards it.
- P6: a payment allocates to invoices in one transaction; over-allocation is checked under a
  `FOR UPDATE` lock on each invoice, so concurrent payments can't both exceed the total. Outstanding
  is **derived** (invoice total − SUM(allocations) over non-cancelled invoices), never stored.
  Payments post nothing to the ledger. `payment`/`payment_allocation` are append-only at the DB.
- P6 is the **benchmark gate**: `pytest -m benchmark` is fully green (B1–B13 + salesman-403 +
  invariants). The ledger-auditor confirmed no P6 break (21 guards). Known gap: `POST /payments` has
  no idempotency key yet (can't drift money; deferred to P8 with the offline queue).
- P7: reports are read-only and render through one envelope (columns + rows + totals), so JSON, CSV
  (stdlib `csv`) and XLSX (openpyxl) are the same table. The stock summary is computed from the same
  ledger the balances use — opening/period/closing tile the timeline — so it reconciles by
  construction. The invoice PDF (fpdf2 + a bundled DejaVu TTF for ₹) is generated on request; the
  font is committed under `app/billing/fonts` (binary in `.gitattributes`) and ships via `COPY backend/`.
- P7 (after the ledger-auditor, 24 guards, no break): the reports/exports/PDF agree with the ledger and
  invoices and write nothing. Presentation notes for P10: the sales register totals are gross (cancelled
  invoices listed with status), and a dispatch cancelled in-period shows gross issues + a reversal
  adjustment (closing stays exact).

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- P5 and P6 are pushed and the live deploy was verified 2026-11-24 (`/api/v1/health` ok; a P6 route
  returns 401, so the P6 build is live; migrations `211c1ab490c2`/`c2c35bc2ef1c`/`7594a71dfb10` applied).
  P7 adds **no migration** but new runtime deps (fpdf2, openpyxl) and the bundled font: after pushing P7,
  confirm the Render image rebuilt and `/api/v1/health` is still ok.
- Render: Health Check Path is still empty; set it to `/api/v1/health` in the dashboard (optional, recommended).
- Live DB: migrations run on every deploy, but Neon is **not seeded**, so the live site has no logins yet.
  Decide by P8: run `python -m app.seed` against Neon from a local shell, or seed at startup behind an env flag.
- **Benchmark gate is green** (`pytest -m benchmark`, no xfail left). The scenario now runs through step 8
  (payment, overheads, cost) and stops at step 9 (`/reports/*`, P7); no benchmark check depends on step 9.
- `POST /payments` has no `Idempotency-Key` yet, so a retry posts a second receipt (it can't drift money —
  over-allocation caps the committed sum at the invoice total). Add it in P8 with the offline queue.
- WIP gap (no test): materials issued to a run that never completes have left stock and show in no report
  (no work-in-progress account, no **run** reversal yet). Invoice-cancellation reversals landed in P5
  (`post_reversals()`); a run reversal would reuse the same primitive.
- Not built yet: the frontend and the offline order queue (P8); README + design note + demo script (P9);
  edit/deactivate endpoints for masters (create only so far); net-sales / GST summary / ageing (P10).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 322 passed, 0 xfailed (2026-11-24). **`pytest -m benchmark` is fully green.** With the P7
report endpoints the scenario now runs end to end (all 9 steps, reports included); no benchmark check
depends on step 9, but it no longer stops the run.

| Check | Status |
|---|---|
| Ledger reconciles / no orphans after every step | ✅ pass |
| B1–B6 (closing balances, FG after run) | ✅ pass |
| B7 (FG 238 → 88 after dispatch) | ✅ pass |
| B8, B9, B9b (yield and consumption variance) | ✅ pass |
| B10, B10b (Retailer A invoice CGST+SGST, number `FF/2026-27/0001`) | ✅ pass |
| B11 (Retailer A outstanding ₹3,875 after a ₹4,000 payment) | ✅ pass |
| B12, B12b (Distributor B shortage 32; INTER tax preview IGST 300) | ✅ pass |
| B13 (cost per packet ₹31.14 through the full scenario) | ✅ pass |
| Salesman 403 on approve | ✅ pass |
| B1–B13 run end to end incl. reports (step 9) | ✅ pass |
| ledger-auditor P4 / P5 / P6 / P7 | ✅ books trustworthy (56 / 17 / 21 / 24 guards green) |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
The whole must-have BACKEND is done and the benchmark gate is GREEN. P8 is the thin FRONTEND (plain JS,
no TypeScript) + the minimal offline order queue — it changes no expected number and adds no backend
behaviour except, optionally, an Idempotency-Key on POST /payments (closing the known P6 gap). Start
phase P8 on branch feat/p8-frontend, as defined in docs/roadmap.md (~3 h; WARN me first if it may not fit,
and commit per screen). Frontend is thin: all business rules stay in the API.
- frontend/src (React + Vite + Tailwind, React Router, a fetch wrapper in src/api/): login per role
  (store the JWT; the role comes from /auth/login). Screens by role (spec section 2):
  - salesman (mobile-first, order in <1 min): pick customer + products from the price list, place the order.
    Minimal OFFLINE QUEUE: each order gets client_uuid = crypto.randomUUID(), queued in localStorage and sent
    as the Idempotency-Key; on reconnect it replays (same key + same body -> the server returns the first
    order, so a double-send lands once). A "pending sync" count is a nice touch.
  - admin: approval queue -> approve (shows the stock-cover shortage) -> raise invoice -> dispatch -> record
    payment; link to the invoice PDF.
  - production: start run / complete run / add overheads; see variance and cost.
  - stock + reports: stock summary and ledger, with the CSV/XLSX download buttons.
- Keep the existing benchmark + API tests green; add a small offline-replay test (a queued order sent twice
  with one key creates one order). Run `cd frontend && npm run lint` and `npm run build`.
If time is short, shrink to the salesman order screen + the admin approve/invoice/dispatch screens; reports
stay API + download (roadmap cut note).
Then run the ledger-auditor subagent only if P8 touched any server code (e.g. the payments Idempotency-Key);
the frontend itself holds no ledger logic.
Finish with tests and lint green (backend and frontend), /update-docs-and-commit, merge to main (ask before
pushing), the teaching protocol, and an updated next prompt for P9 (README + design note + demo script).
```
