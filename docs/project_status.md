# Project status (session handoff file)

_Last updated: 2026-11-24_

## Current phase: P6 done — **benchmark gate GREEN** (ledger-audited). Next: **P7 reports + invoice PDF**

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
| P7 | Invoice PDF + reports (registers, stock, production) + CSV/XLSX export | ⚪ next |
| P8–P9 | Frontend + offline queue → README/design note/deploy | ⚪ |
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

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- P5 is pushed (Render redeploying). After pushing P6, confirm the deploy is live and the three new
  migrations (`211c1ab490c2` sales, `c2c35bc2ef1c` billing, `7594a71dfb10` payments) applied on Neon.
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
- Not built yet: reports and invoice PDF (P7); the frontend and the offline order queue (P8);
  edit/deactivate endpoints for masters (create only so far).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 290 passed, 0 xfailed (2026-11-24). **`pytest -m benchmark` is fully green — the benchmark
gate is passed.** The scenario runs through step 8 (payment, overheads, cost) and stops at step 9
(`/reports/*`, P7); no benchmark check depends on step 9.

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
| ledger-auditor P4 / P5 / P6 | ✅ books trustworthy (56 / 17 / 21 guards green) |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
The benchmark gate is already GREEN (pytest -m benchmark all pass); P7 adds deliverables on top, so keep
every benchmark check green and change no expected number. Start phase P7 on branch feat/p7-reports,
exactly as defined in docs/roadmap.md (~1.25 h; commit per piece). Follow the stock-ledger and gst-rules
skills; read, never write, the ledger.
- reports: GET /reports/sales-register, /reports/stock-summary, /reports/stock-ledger, /reports/production,
  each taking {from, to} (the benchmark calls all four as the accountant in step 9 with 2026-11-01..30).
  Read-only for auditor/admin/owner. The stock summary must equal SUM(ledger) per item (opening + receipts
  - issues +/- adjustments = closing, each ledger row linked to its source doc) and reconcile in a test.
  CSV + XLSX export (stdlib csv + openpyxl) behind a ?format=csv|xlsx param (M8).
- invoice PDF (fpdf2 + the bundled DejaVu TTF for the rupee glyph): GET /invoices/{id}/pdf with GSTIN, HSN,
  taxable value, CGST+SGST or IGST, and the FY number. Generated on request (Render has no disk). Optional
  wow: a wa.me share link carrying the PDF URL.
Match the step-9 report paths/params in tests/benchmark/test_section5.py (don't change expected numbers);
once the four report endpoints exist the scenario runs end to end (step 9 no longer stops it). No xfail
markers remain to remove. Then run the ledger-auditor subagent (attacks: a report total that disagrees with
the ledger, an export that drops/duplicates rows, a PDF whose line taxes don't sum to its total) and fix
what it confirms.
Finish with tests and lint green, run the benchmark-check skill, /update-docs-and-commit, merge to main
(ask before pushing), the teaching protocol, and an updated next prompt for P8.
```
