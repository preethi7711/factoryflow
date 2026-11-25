# Project status (session handoff file)

_Last updated: 2026-11-25 (UI upgrade done)_

## Current phase: UI upgrade done — Pouch & Process redesign. Next: **P10 (should-haves)**

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
| P8 | Frontend (thin): login, salesman mobile order + offline queue, admin/production/stock screens | ✅ done |
| P9 | README + design note + demo script + UI fixes for benchmark steps 1–3, 6, 7 + seed-on-start | ✅ done, live and seeded |
| UI | Frontend upgrade, design direction C "Pouch & Process", same flows | ✅ done |
| P10–P11 | Should-haves → stretch | ⚪ next |

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
- P8: the frontend is thin plain JS (React + Vite + Tailwind + React Router) — all rules stay in the API.
  One fetch wrapper carries the JWT; routes are role-gated. The offline order queue lives in localStorage:
  each order's `client_uuid` is the `Idempotency-Key`, so the queue retries freely and the server replays
  (one order). No service worker yet — "minimal offline queue" is the localStorage queue + online/offline
  events; a full PWA shell cache is a later polish. The admin flow keeps the raised invoice in session
  state to drive dispatch/payment (there is no list-invoices endpoint yet; a reload before dispatch needs
  one — fine for the demo, a GET /invoices filter would make it robust). Verified in a browser.
- P8 did **not** add the payments `Idempotency-Key`; it stayed a known gap (can't drift money). Fold it in
  with any P9/P10 hardening if the offline queue is extended to payments.

- P9: the screens could not show benchmark steps 1–3, 6 and 7 exactly (no purchase screen; the run issued
  the full BOM with no field for 10.5 l oil / 194 pouches / 6 damaged / 9 cartons; payment always paid the
  full total). Fixed in the frontend only, using inputs the API already accepted; the whole scenario was
  then driven in a browser on a fresh dev DB and every number matched. Money typed in the UI is parsed to
  paise from text (`toPaise`), quantities are multiplied as exact decimal strings (`decMul`), and dates use
  the local calendar day (`localToday`; `toISOString()` gave the UTC day, which made November reports start
  on 31 Oct). The offline queue is per salesman (`ff.order.queue.<username>`).
- P9: the live DB is seeded by the production image when `SEED_ON_START=1` (idempotent: skipped once
  users exist). Chosen over seeding Neon from a laptop so the database URL never leaves Render.
- P9 lesson: the local dev DB had an early draft of the append-only migration (applied before the file
  was final), so purchases failed locally only. Rebuilt the dev schema from the migrations. Rule: if a
  migration file changes after you ran it, reset the dev DB (`DROP SCHEMA public CASCADE` + upgrade + seed).

- UI: design direction C "Pouch & Process". Tokens in `tailwind.config.js`; self-hosted Bricolage Grotesque +
  Hind Madurai (fontsource, OFL-1.1). Original inline SVGs (`SnackArt.jsx`) keyed to item code/name via regex.
  Motion is state-driven only: process-line pipe dashes while run is DRAFT, packet count pops on change,
  animations wrapped in `motion-safe:` or the reduced-motion CSS block.
- UI: `memory.js` localStorage helpers (`remember`/`recall`, try/catch) used for the last run id
  (`ff.run.{username}`) and invoice map (`ff.invoices`), so the production and admin pages survive a reload.
- UI: `showQty(qty, uom)` in `format.js` converts base units (g→kg, ml→l) for display; the stock summary
  shows human units and ₹ values while downloads keep the raw base-unit numbers.
- UI: single-product price list uses `grid-cols-1`; nav pills are `whitespace-nowrap`; stock table uses
  `min-w-max` inside `overflow-x-auto` for correct horizontal scroll on mobile.

## Open issues
- **Live site seeded and verified 2026-11-24:** P9 deployed (new bundle served), `SEED_ON_START=1` and
  `SEED_DEMO_PASSWORD=factoryflow-demo` set on Render, `admin` login confirmed by the user. Optional: set
  `SEED_ON_START=0` and Health Check Path `/api/v1/health` in the dashboard.
- Hours/day unconfirmed (assumed ~6, H1).
- P5–P7 are pushed; the live deploy was verified 2026-11-24 up to P6 (`/api/v1/health` ok, a P6 route 401s,
  migrations `211c1ab490c2`/`c2c35bc2ef1c`/`7594a71dfb10` applied). P7 (fpdf2/openpyxl + font) and P8
  (frontend) add **no migration**; after pushing them confirm the Render image rebuilt and `/` serves the
  new UI. The P7 deploy was not separately re-verified.
- **Local dev gotcha:** `docker compose up` does NOT run migrations (only the production image does on start).
  After pulling new migrations, run `docker compose exec api alembic upgrade head` or the dev DB lags — P8's
  browser test hit a 500 because the dev DB was missing the `payment` table until migrated.
- Admin UI: invoice persistence now survives a reload via `memory.js` (localStorage) + `GET /invoices/{id}`
  re-read on load; a `GET /invoices?order_id=` filter would handle a different browser too.
- **Benchmark gate is green** (`pytest -m benchmark`, no xfail left). The scenario now runs through step 8
  (payment, overheads, cost) and stops at step 9 (`/reports/*`, P7); no benchmark check depends on step 9.
- `POST /payments` has no `Idempotency-Key` yet, so a retry posts a second receipt (it can't drift money —
  over-allocation caps the committed sum at the invoice total). Add it in P8 with the offline queue.
- WIP gap (no test): materials issued to a run that never completes have left stock and show in no report
  (no work-in-progress account, no **run** reversal yet). Invoice-cancellation reversals landed in P5
  (`post_reversals()`); a run reversal would reuse the same primitive.
- Demo: the admin page now re-reads the invoice from the server on reload (via `memory.js` + `GET /invoices/{id}`),
  so a browser reload between steps 5 and 7 is safe. Still use a separate browser for the salesman (docs/demo_script.md).
- Stock summary now displays kg/l and ₹ via `showQty`/`inr` helpers (fixed in UI upgrade).
- Not built yet: a service-worker PWA shell (P8 did the
  localStorage queue only); edit/deactivate endpoints for masters (create only so far); payments
  Idempotency-Key; net-sales / GST summary / ageing (P10).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 322 passed (2026-11-24, P9; no backend change in UI). **`pytest -m benchmark`: 19 passed** (re-verified 2026-11-25). Frontend: `npm run test` 9 passed (added `showQty` tests), lint and build clean. **All nine benchmark steps re-verified through the new UI** on the dev DB: flour 120 kg, oil 19.5 l, spice 3.8 kg, pouches 306, cartons 21, FG 238 → 88; variance −6.00% / +5.00% flagged, pouches −3.00% not; invoice FF/2026-27/0001 ₹7,875; outstanding ₹3,875; Distributor B short 32 / IGST ₹300; cost ₹31.14, margin ₹18.86.

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
UI upgrade (design direction C "Pouch & Process") is done on branch feat/ui-pouch-process. The branch
has not been pushed yet — ask the user whether to push and merge to main first.
Then start P10 (should-haves). Prioritise: S4 GST summary (GSTR-1 B2B + HSN rows, 3B 3.1a totals),
S2 payments register + ageing, S6 owner dashboard (key metrics from existing endpoints). No backend
schema changes needed for these — they are read-only report endpoints and a dashboard page.
Hard rules: benchmark stays green; no paid services; ask before pushing.
```
