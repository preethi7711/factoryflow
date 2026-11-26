# Changelog

All notable changes, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Each milestone adds a section. Commit hashes are in `git log`.

## [Unreleased]

### Added (P11 stretch — Tally day book)
- `reports.service.tally_daybook` + `GET /reports/tally-daybook`: one row per voucher in period
  (non-cancelled Sales invoices, Purchases, customer Receipts), sorted chronologically. Dates are
  formatted DD-MM-YYYY, Tally's standard. Amounts stay integer paise on the wire (the accountant
  divides by 100 at import). Cancelled sales are excluded, matching the GST summaries.
- StockPage tab bar: new "Tally day book" tab (11 tabs total). Download via the shared CSV/XLSX
  pipeline — no bespoke exporter needed.
- 2 new integration tests (daybook row shape, CSV totals).

### Added (P11 stretch — masters edit/deactivate)
- Migration `c932ce0a5ca4`: adds `is_active BOOLEAN NOT NULL DEFAULT TRUE` to `item`, `customer`,
  `supplier`. Existing rows become active; no behaviour change until an admin edits one.
- `PATCH /items/{id}`, `PATCH /customers/{id}`, `PATCH /suppliers/{id}` (admin only). Each PATCH
  takes a subset of fields; `code`, `kind` and `base_uom` (items only) are immutable because they
  are structural identifiers that invoices, lots and the ledger point at.
- List endpoints (`/items`, `/customers`, `/suppliers`) default to active-only, with
  `?include_inactive=true` to see everything (so an admin can find a deactivated row and reactivate
  it). The price list excludes inactive FGs.
- Every PATCH is audit-logged with before→after. Historical documents (orders, invoices, lots,
  purchases) never look at `is_active`, so deactivating a master leaves all prior figures intact.
- 10 new integration tests cover edit, deactivate, `include_inactive`, salesman reassignment,
  invalid salesman, role gating, 404s.

### Changed (P11 stretch — payments idempotency)
- `POST /payments` now requires an `Idempotency-Key` header, same shape as `POST /orders`. A
  replayed key with the same body returns the first receipt (never a second one); a different body
  under the same key is a 409 `IDEMPOTENCY_CONFLICT`; a key belongs to the user who first used it
  (403 if another user presents it). Shares the `idempotency_key` table with orders (`route` tells
  them apart). A concurrent double-tap under the same key is caught as `IntegrityError` and replays
  the winner — never 500s. The admin UI sends `crypto.randomUUID()` on each receipt. Closes the
  P8-era known gap. 4 new API tests (required / replay / conflict / cross-user).

### Added (P11 stretch — first slice)
- `reports.service.purchase_register` + `/reports/purchase-register` (S1): one row per purchase in
  period with supplier, GSTIN, supply type, line count and tax split. Totals come straight from the
  Purchase document (stored at receipt), so they match what the ledger capitalised.
- `reports.service.variance_alerts` + `/reports/variance-alerts` (S5): one row per flagged yield or
  material line across all completed runs in period. Re-uses `production.run_variance()`, so the
  alerts can't disagree with the per-run variance screen.
- Dashboard: `flagged_variances` field surfaces as an info banner on `DashboardPage` with a pointer
  to Stock & reports → Variance alerts.
- Frontend `StockPage`: Purchases and Variance alerts tabs added (10 tabs total).

### Added (P10 should-haves)
- `reports.service.gst_summary` + `/reports/gst-summary`: non-cancelled invoices of the period with
  their tax split; the totals row is GSTR-3B table 3.1(a) (taxable + CGST + SGST + IGST + total).
- `reports.service.hsn_summary` + `/reports/hsn-summary`: invoice lines grouped by (HSN × UOM ×
  rate), the GSTR-1 table 12 shape.
- `reports.service.payments_register` + `/reports/payments-register`: every receipt of the period
  with its invoice allocations spelled out ("applied to INV-x").
- `reports.service.ageing` + `/reports/ageing`: each unpaid, non-cancelled invoice bucketed by
  (`to` − invoice_date) into 0-30 / 31-60 / 61-90 / 91+ days; outstanding derived from allocations,
  the same source of truth payments.service uses.
- `reports.service.dashboard` + `/reports/dashboard`: at-a-glance numbers for the owner (FG qty +
  value, pending orders, sales + collections + outstanding, completed runs).
- Frontend `DashboardPage` (`/dashboard`, owner + admin): four metric cards, FG-on-hand list,
  compact ageing panel. Owner's `HOME` is now `/dashboard`.
- Frontend `StockPage`: tab bar across all eight reports with inline rendering from the shared
  `{columns, rows, totals}` envelope — one `ReportTable` component, no per-report code.

### Added (UI upgrade — design direction C "Pouch & Process")
- Design tokens: turmeric / chilli / leaf / choc palette + cream / paper backgrounds in `tailwind.config.js`;
  keyframes `pop`, `flow`, `fade-in`, `spin-slow`; self-hosted Bricolage Grotesque + Hind Madurai (fontsource).
- `SnackArt.jsx`: original inline SVGs for murukku, mixture, chips, flour, oil, spice, pouch, carton + sack
  fallback; `artFor()` keyed to item code/name via regex; `Logo` component used in header and login.
- `Layout.jsx`: sticky header with Logo + wordmark, role nav pills (turmeric-100 when active), `whitespace-nowrap`
  to prevent pill wrap on mobile; `max-w-lg` for salesman (cream bg), `max-w-5xl` for desk roles (paper bg).
- `LoginPage.jsx`: cream background, turmeric kolam strip, logo, tagline.
- `OrderPage.jsx`: turmeric welcome strip with kolam overlay and slow-spinning murukku (`motion-safe`);
  customer radio chips; illustrated `ProductCard` (ItemArt, price+GST%, −/+/input step buttons, +10 shortcut);
  `grid-cols-1` for single-product lists; sticky `OrderBar`; `Timeline` progress rail; `QueueList`;
  "Sales by customer" summary from server orders.
- `RunVisuals.jsx` (`ProcessLine`, `VarianceBars`, `CostBreakdown`): process line with animated SVG pipe dashes
  while run is DRAFT; planned vs actual bars in leaf/chilli with flagging text; stacked cost bar + dark panel
  showing cost per packet and margin.
- `ProductionPage.jsx`: full redesign with ItemArt in `QtyTable`, item names instead of codes, `ProcessLine`
  at the top, variance and overheads cards in a grid after completion, run re-read from server on login via
  `memory.js` (`ff.run.{username}`).
- `AdminOrdersPage.jsx`: `Pill` status badges, ItemArt per order line, invoice persistence via `memory.js`
  (`ff.invoices`) + `GET /invoices/{id}` re-read on load.
- `StockPage.jsx`: `showQty`/`inr` formatting (kg/l and ₹), ItemArt beside item code, right-aligned numeric
  columns, `min-w-max` on table for correct horizontal scroll on mobile.
- `memory.js`: `remember`/`recall` localStorage helpers (try/catch wrapped).
- `format.js`: `showQty(qty, uom)` converts g→kg, ml→l; negative-sign handled before conversion.
- `docs/DESIGN.md`: palette, type, layout per role, illustration rules, motion rules, accessibility,
  component inventory, known gaps.

### Fixed (UI upgrade)
- Stock summary now shows kg / l and ₹ instead of raw g / ml / paise.
- Admin invoice re-read from server on page reload; a page reload between dispatch and payment no longer
  loses the invoice.
- Nav pills no longer wrap on narrow viewports.
- Stock table scrolls horizontally on mobile instead of squashing column widths.

### Added (P9)
- `README.md`, `docs/design_note.md`, `docs/demo_script.md` (deliverables 2–4).
- Production screen: purchase card (benchmark step 1); editable raw issues at start, packaging used +
  damaged at completion, full planned-vs-actual variance table in kg/l.
- Admin: part payments with the server's outstanding; invoice tax split; IGST tax preview on a shortage.
- Production image: optional idempotent seed on start (`SEED_ON_START=1`).

### Fixed (P9)
- UI money parsed to paise from text (no float); quantities multiplied as exact decimals; local (IST)
  dates instead of UTC, which had also made the month's reports start on the last day of the previous month.
- Offline order queue is per salesman, so one browser can't show or send another salesman's orders.

### Added
- P8 frontend (React + Vite + Tailwind + React Router, plain JS; business rules stay in the API): JWT login
  per role with role-gated routes, and one `fetch` wrapper (`src/api/client.js`: `ApiError`, plus `apiBlob`
  for the auth-protected PDF/exports).
- Salesman (mobile-first) order screen priced from the price list for the salesman's own customers, with a
  **minimal offline queue** (`src/offline/queue.js`): each order carries a `client_uuid` kept in localStorage
  and sent as the `Idempotency-Key`; it flushes on load and on reconnect, and because the key is stable a
  retry replays server-side, so a double-send lands exactly one order. Vitest covers the replay.
- Admin: approval queue → approve (shows the stock shortage) → raise invoice → dispatch → record payment,
  with a "view invoice PDF" that opens the authed blob. Production: start/complete run + overheads → cost per
  packet and yield variance. Stock & reports: the stock summary table with CSV/XLSX download buttons.
- Frontend tooling: ESLint (flat) + Prettier + Vitest; `npm run lint` / `build` / `test`. The salesman order
  (queue → synced) and the full admin approve→invoice(FF/2026-27/0001)→dispatch→payment flow were verified in
  a browser against the seeded dev DB. No backend behaviour changed.

## P7 reports, invoice PDF

### Added
- P7 `reports` (read-only; auditor/admin/owner): `GET /reports/{sales-register,stock-summary,stock-ledger,
  production}` with `{from,to}`. A uniform envelope (columns + rows + totals) renders as JSON, or as CSV
  (stdlib `csv`, utf-8-sig) or XLSX (openpyxl) behind `?format=`. The stock summary reconciles to the ledger
  (opening + receipts − issues ± adjustments == closing == SUM(ledger)); the production report reuses
  `production.service` for cost and variance; the sales register sums per column.
- P7 `billing`: `GET /invoices/{id}/pdf` — the GST tax invoice as a PDF (fpdf2 + a bundled DejaVu TTF so the
  rupee sign renders), generated on request (Render has no disk). GSTIN, HSN, taxable, CGST+SGST or IGST, FY
  number; the printed lines sum to the printed total.
- deps: fpdf2==2.8.2, openpyxl==3.1.5 (architecture §2); `DejaVuSans.ttf` bundled under `app/billing/fonts`,
  marked binary in `.gitattributes`.
- With the four report endpoints the benchmark scenario runs end to end (step 9 no longer stops it); every
  benchmark check stays green.
- `ledger-auditor` P7 suite in `tests/audit/` (24 guards; no break — reports/exports/PDF agree with the
  ledger and invoices, and wrote nothing).

### Notes (not breaks, for P10)
- The sales register totals are gross (a cancelled invoice is still listed, with its status), and a dispatch
  cancelled within the period shows as a gross issue plus a reversal adjustment (closing stays exact). Net
  sales / collections belong in the P10 GST summary and ageing work.

## P6 payments (benchmark gate)

### Added
- P6 `payments`: `POST /payments` (admin) — record a receipt and allocate it to the customer's invoices
  in one transaction. Validates allocations sum to the amount, rejects a duplicate invoice, a non-positive
  amount, a cancelled invoice, an invoice of another customer, and over-allocation (allocated + new >
  invoice total, 409), checked under a `FOR UPDATE` row lock so concurrent payments to one invoice can't
  both slip past. `GET /customers/{id}/outstanding` (admin/auditor/owner): outstanding is **derived** —
  invoice total − SUM(allocations) over non-cancelled invoices, with a per-invoice breakdown. Payments post
  nothing to the stock ledger. `payment` and `payment_allocation` are append-only at the DB.
- **Benchmark gate reached:** removing the B11 and B13 xfail markers makes scenario steps 7–8 reachable, so
  `pytest -m benchmark` is now entirely green (B1–B13 + salesman-403 + the ledger invariants). B11 outstanding
  ₹3,875; B13 cost ₹31.14 now asserted through the full scenario.
- `ledger-auditor` P6 hostile audit suite in `tests/audit/` (21 guards; no break confirmed).

### Known
- `POST /payments` has no `Idempotency-Key` yet, so a retry posts a second receipt; it cannot drift money
  (over-allocation caps the committed sum at the invoice total). Deferred to P8 with the offline queue.

## P5 sales, billing (invoice, dispatch, credit notes)

### Added
- P5 `sales`: `POST /orders` (salesman/admin), each line priced by the server from the price list;
  idempotent via the `Idempotency-Key` header (stored as `sales_order.client_uuid` UNIQUE plus an
  `idempotency_key` table — same key + same body replays, different body → 409). `GET /orders` and
  `GET /orders/{id}` (a salesman sees only their own customers' orders). `POST /orders/{id}/approve`
  (admin; salesman → 403) with a stock-cover check → 409 `INSUFFICIENT_STOCK` carrying
  requested/available/shortage (B12). `GET /orders/{id}/tax-preview` (B12b).
- P5 `billing`: `POST /orders/{id}/invoice` (gapless FY number `FF/2026-27/0001` via a row-locked
  `invoice_sequence`; per-line CGST+SGST or IGST by place of supply — B10, B10b), `GET /invoices/{id}`,
  `POST /invoices/{id}/dispatch` (DISPATCH movements; B7: FG 238→88), `POST /invoices/{id}/cancel`
  (credit note + REVERSAL movements that mirror the dispatch exactly; invoice number stays used, A12).
- `inventory.post_reversals()`: the only writer of REVERSAL movements (same lot, opposite qty and value,
  linked by `reverses_id`, UNIQUE so a movement is reversed at most once). `KNOWN_SOURCE_TABLES` and the
  orphan invariant now cover `dispatch` and `credit_note`.
- Benchmark: B7, B10, B10b, B12, B12b and the salesman-403 check pass; only B11 and B13 stay xfail (P6).
- `ledger-auditor` P5 hostile audit suite in `tests/audit/` (17 guards: idempotency replay, reversal
  symmetry, invoice numbering, backdated dispatch, and the standing ledger invariants).

### Fixed
- P5 ledger-audit findings (all three, tests now green): a backdated, out-of-order dispatch can no longer
  drive a lot negative — an outflow now checks the current per-lot balance as well as the as-of-date one
  (a lot has one inflow, so now is its lowest point); an idempotent double-tap's losing caller replays
  instead of 500-ing (the `IntegrityError`→replay guard wraps the flush, not just the commit); replay is
  scoped to the user who owns the key (another user presenting it → 403).

## P4 purchases and production runs

### Added
- P4 `purchasing`: `POST /purchases`, `GET /purchases/{id}`. One lot per line, stock in base units at the
  quoted-unit value, input GST (CGST+SGST or IGST by supplier state) recorded but not costed (A15).
- P4 `production`: `POST /production-runs` (start + raw issues), `POST /{id}/complete` (packaging issues,
  damaged info, FG lot with expiry, OUTPUT at material cost), `POST /{id}/overheads` (COST_ADJUST),
  `GET /{id}`, `/variance` (B8, B9, B9b, A4) and `/cost` (B13: ₹31.14). Actual consumption is read from the
  ledger. Every step is audit-logged; a run can't be completed twice.
- Benchmark: B1–B6, B8, B9, B9b pass. B13 is proven by `tests/integration/test_production.py`.
- `core/clock.py` (IST business time); stock errors name the short item; assumption A18 (overhead date).
- `ledger-auditor` P4 hostile audit suite in `tests/audit/` (56 tests: 47 guards + 9 findings).

### Fixed
- P4 ledger-audit findings (all 9, tests now green): backdated issues can no longer overdraw stock
  on the movement date (balances read as of `movement_date`); `post_movements()` refuses an unknown
  source document and the orphan invariant actually checks existence; posted documents are append-only
  at the DB (a completed run or a purchase can't be edited or deleted, so `/cost` and `/variance` can't
  diverge from the ledger); concurrent posts lock items before inserting, so one gets 409 instead of a
  deadlock 500; one rounding point per issue line; whole-number pcs/pkt; `COST_ADJUST` must add value;
  BOMs are admin-only (segregation of duties).

## P3 auth, masters, ledger, audit, seed

### Added
- P3 `auth`: `app_user` with 5 roles, bcrypt passwords, JWT login (`POST /auth/login`, `GET /auth/me`),
  `require_roles()` deny-by-default, a test that fails if any route forgets it, and a role matrix test.
- P3 `masters`: items (+ pack units), BOMs stored in base units (one active per product), customers and
  suppliers (soft GSTIN warnings), price list (`item.sale_price_paise`), company settings. GET + POST endpoints.
- P3 `inventory`: `stock_movement` ledger (append-only trigger, composite lot/item FK, sign CHECK,
  `movement_date`), lots, `stock_adjustment` documents, `post_movements()` as the only writer (item locks,
  FIFO lot allocation, WAC values, anti-drift), `balance()`, `reconcile()`, `GET /stock/balance/{id}`,
  `GET /stock/reconcile`.
- P3 `audit`: append-only `audit_log`, written in the same transaction as the change.
- Seed (`python -m app.seed`): PROBLEM §5 masters, opening stock as an OPENING document, six demo logins.
- Error format `{"error": {"code", "message", "details"}}` for every failure, including 404/422.
- Ledger invariants (reconcile, API = SUM(ledger), no orphans) checked after every benchmark step and after
  every integration test. Benchmark: reconcile and orphan checks now pass.
- Production refuses to start with a weak `JWT_SECRET_KEY` (32+ characters), without logging any value.
- Assumptions A16 (shelf life 90 days) and A17 (opening stock dated 31 Oct 2026).

## P2 core maths

### Added
- P2 core maths in `backend/app/core/` (pure, no DB/HTTP): `money` (paise, half-up, Indian ₹ format),
  `units` (Decimal `to_base`/`from_base`, item packs, cross-dimension errors, floats refused), `gst`
  (INTRA/INTER, per-line tax, FY, invoice numbers, soft GSTIN checks), `wac` (receipt/issue value with
  anti-drift, cost per unit), `variance` (bp + strict exact-value flag). 64 unit tests, incl. B8–B10, B12b,
  B13 and A5 arithmetic.

### Changed
- Architecture: variance flag uses exact values; rounding points listed in one place.

## P1b deploy

### Added
- P1b: root multi-stage `Dockerfile` (Node builds `frontend/`, slim Python serves API + built files as a
  non-root user, listens on `$PORT`, runs `alembic upgrade head` on start) and root `.dockerignore`.
- Placeholder React + Vite frontend (`frontend/`) showing live API/DB health.
- FastAPI serves the built app (`STATIC_DIR`) with an index.html fallback for client routes; `/api` stays JSON 404.
- `DATABASE_URL` from hosts (`postgres://`, `postgresql://`) is rewritten to the psycopg 3 driver.
- CI job that builds the production image.
- Deployed: https://factoryflow-icdx.onrender.com (Render Free + Neon Free), health and page verified live.

### Fixed
- First Render deploy failed (`open Dockerfile: no such file or directory`): the service's Root Directory
  was `docker/`. Cleared it in the Render dashboard; no code change.

## P1 skeleton

### Added
- P1 skeleton: `docker-compose.yml` (db + api, test DB created on first start, `API_PORT` override),
  FastAPI app with `GET /api/v1/health` (checks the DB), typed settings from env, Alembic wiring (no tables yet).
- pytest on a separate `factoryflow_test` DB rebuilt by migrations; ruff config; GitHub Actions CI
  (lint + tests on Postgres 16).
- `backend/tests/benchmark/test_section5.py`: PROBLEM §5 steps 1–9 through the HTTP API, every spec §4
  check as its own `xfail(strict=True)` test.
- Claude Code project hooks (`.claude/settings.json`): block edits to `docs/PROBLEM.md` and `.env*`
  (except `.env.example`); ruff format + fix on edited `.py` files.
- `docs/interview_notes.md` (teaching protocol output, starting with P1).

### Changed
- `.env.example`: added `TEST_DATABASE_URL`.

## Phase 0

### Added
- Phase 0 setup: problem statement (verbatim), `CLAUDE.md`, `.env.example`, `.gitignore`, `.gitattributes`.
- Docs: `project_spec.md` (requirements, tiers, benchmark numbers, assumptions), `architecture.md` (provisional),
  `project_status.md`, this changelog.
- Claude Code slash command `/update-docs-and-commit`.
- Approved plan: `architecture.md` (stack, hosting, ER diagram, invariant mechanisms), `roadmap.md`
  (P1–P11, cut lines, wow list, teaching protocol), spec test logins and assumptions A13–A15, H1.
- Project skills `stock-ledger`, `gst-rules`, `benchmark-check`, and subagent `ledger-auditor`.

### Changed
- A5: opening finished goods valued at standard material cost ₹19.85/pkt.
- Offline order queue moved from stretch into P8 (§4.1 "strongly preferred").
- CLAUDE.md: plain JS frontend, single deployable, hosting, handoff and xfail rules.
