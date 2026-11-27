# FactoryFlow: order-to-audit for a small snack factory

FactoryFlow takes a South Indian snack manufacturer from a salesman's order to the auditor's month-end
reports. Every transaction is entered once, where it happens, and flows into stock, production
costing and accounts. Built for the NIT Tiruchirappalli CDI internship task ([problem statement](docs/PROBLEM.md)).

**Live demo:** https://factoryflow-icdx.onrender.com
The free tier sleeps after 15 minutes idle, so the **first load can take about a minute**. Later
loads are fast.

## Test logins

All six accounts share one password: **`factoryflow-demo`** on the live site, and `SEED_DEMO_PASSWORD`
from your `.env` locally (`demo-change-me` by default). These are demo credentials for dummy data only.

| Username | Role | Sees |
|---|---|---|
| `salesman_a` | salesman | mobile order screen; owns Retailer A (Tamil Nadu) |
| `salesman_b` | salesman | mobile order screen; owns Distributor B (Karnataka) |
| `admin` | admin | order approval, GST invoice, dispatch, payments, stock & reports |
| `production` | production | purchases, production runs, variance, cost per packet |
| `accountant` | auditor (read-only) | stock summary and report exports |
| `owner` | owner (read-only) | stock summary and report exports |

## Run it locally

Prerequisites: Docker Desktop (Compose v2), Node 20+.

```bash
git clone https://github.com/preethi7711/factoryflow.git
cd factoryflow
cp .env.example .env                                   # Windows PowerShell: Copy-Item .env.example .env
docker compose up -d                                   # Postgres + API on http://localhost:8000
docker compose exec api alembic upgrade head           # the dev DB does not auto-migrate
docker compose exec api python -m app.seed             # section 5 master data + the six logins
cd frontend && npm install && npm run dev              # web app on http://localhost:5173
```

API docs (OpenAPI) are at http://localhost:8000/docs. To run the exact image Render runs:
`docker build -t factoryflow .` (it migrates on start, and seeds when `SEED_ON_START=1`).

## Tests

```bash
docker compose exec api pytest                          # whole backend suite
docker compose exec api pytest -m benchmark -v          # the section 5 scenario, check by check
cd frontend && npm run test                             # money/quantity helpers + offline queue
```

The benchmark test (`backend/tests/benchmark/test_section5.py`) was written **before** the code. It
drives the real HTTP API as each role, runs all nine steps in order, and asserts every number below.
After every step it also checks the ledger invariants: stock = SUM(ledger), every movement has a
source document, nothing is orphaned. A hostile "ledger auditor" suite (`backend/tests/audit/`) adds
tests that try to make stock or money drift.

## Benchmark results (section 5)

| Check | Expected | FactoryFlow |
|---|---|---|
| Flour closing | 120 kg | **120 kg** |
| Oil closing | 19.5 L | **19.5 L** |
| Pouches closing | 306 | **306** (188 used + 6 damaged) |
| Finished goods after run | 238 packets | **238** |
| Finished goods after Retailer A dispatch | 88 packets | **88** |
| Yield variance | 188 vs 200, −6%, flagged | **−6.00%, flagged** |
| Oil consumption variance | +5%, flagged | **+5.00%, flagged** |
| Retailer A invoice | ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875 | **same**, invoice `FF/2026-27/0001` |
| Retailer A outstanding | ₹3,875 | **₹3,875.00** |
| Distributor B order | shortage of 32 flagged; IGST if invoiced | **approval refused: requested 120, available 88, shortage 32**; tax preview = IGST ₹300, total ₹6,300 |
| Cost per packet | your figure | **₹31.14**, margin ₹18.86 (37.7%) at ₹50 |

Also asserted: spice mix 3.8 kg and cartons 21 left; the pouch variance of −3.00% is **not** flagged
(the brief says flag *beyond* 3%).

**How ₹31.14 is computed** (weighted average cost; overheads charged to the run):
- Flour is issued at the moving average after the purchase: (100 × 42 + 60 × 45) / 160 = ₹43.125/kg, so 40 kg = ₹1,725.
- Oil 10.5 L × 140 = ₹1,470. Spice 1.2 kg × 200 = ₹240.
- Pouches 194 × 2.50 = ₹485 (the 6 damaged pouches are a normal loss, charged to the run).
- Cartons 9 × 15 = ₹135.
- Materials total ₹4,055. Labour ₹1,200 and gas/power ₹600 bring the run to ₹5,855.
- ₹5,855 ÷ 188 good packets = ₹31.14.

No result differs from the expected values.

## Stack and why

FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL 16, with a thin React + Vite + Tailwind front end in
plain JavaScript. Python and SQL hold every business rule (stock, tax, costing) where it can be tested,
and Postgres gives exact `NUMERIC` maths, row locks and triggers that make the stock ledger
append-only. In production the API serves the built web app, so it's one free Render service plus a
free Neon Postgres database, with no paid services anywhere. Design details: [design note](docs/design_note.md).

## What's built (against the section 6 tiers)

| Tier | Item | Status |
|---|---|---|
| Must | Login with roles (5 roles, deny by default, checked on every route) | ✅ |
| Must | Product, customer, raw-material and BOM masters | ✅ via API + seed; admin edit screen at `/masters` |
| Must | Mobile-friendly order entry and admin approval | ✅ |
| Must | GST invoice as PDF (GSTIN, HSN, CGST/SGST or IGST, FY numbering) | ✅ |
| Must | Production run updates raw and finished-goods stock automatically | ✅ |
| Must | Planned vs actual consumption and yield, with variance | ✅ |
| Must | Stock summary and stock ledger | ✅ |
| Must | Sales register and stock report, CSV/Excel export | ✅ |
| Should | Purchases and supplier records | ✅ purchases (plus purchase register report) |
| Should | Payments and outstanding | ✅ (receipt `Idempotency-Key` closes the double-post window) |
| Should | Ageing | ✅ 0-30 / 31-60 / 61-90 / 91+ day buckets on `/reports/ageing` |
| Should | Cost per packet with overheads | ✅ |
| Should | GST summary report (GSTR-1 / 3B shape) | ✅ `/reports/gst-summary` (B2B) and `/reports/hsn-summary` (HSN rate buckets) |
| Should | Variance alerts beyond a tolerance | ✅ `/reports/variance-alerts` lists every flagged yield or material line |
| Should | Owner dashboard | ✅ `/dashboard` with sales / collections / outstanding / FG value, ageing panel, variance banner |
| Stretch | Offline order capture with sync | ✅ localStorage queue + idempotency keys |
| Stretch | Batch and expiry tracking | ✅ every movement carries a lot (FIFO; FEFO not switched on) |
| Stretch | Service-worker PWA shell | ✅ `vite-plugin-pwa`: app opens offline, installable on Android/iOS |
| Stretch | Tally day book export | ✅ `/reports/tally-daybook` CSV (DD-MM-YYYY, Sales/Purchase/Receipt vouchers) |
| Stretch | Master data edit / deactivate | ✅ PATCH endpoints + admin UI; deactivation hides from lists but leaves history intact |
| Extra | Invoice cancellation by credit note, audit log, append-only documents | ✅ |

## Assumptions

The full table, with reasons, is in [project_spec.md §5](docs/project_spec.md#5-assumptions-and-ambiguities-to-copy-into-the-readme).
The ones that shape the numbers:

- **A1. Variance basis:** planned quantity = BOM standard × batches. Variance = (actual − planned) / planned.
- **A2. Flagging:** flag when |variance| is strictly greater than the tolerance (3%, configurable per item).
- **A3. Pouches:** 194 used vs 200 standard is exactly −3.00%, so not flagged. The 6-packet shortfall shows up as the −6% yield variance.
- **A4. Cartons:** 9 used vs 10 standard (−10%) is flagged as under-use. 188 packets = 9 full cartons + 8 loose.
- **A5. Opening finished goods:** the 50 opening packets are valued at standard material cost, ₹19.85/packet. This doesn't affect ₹31.14.
- **A6. Valuation:** moving weighted average cost per item. Lots track batches and expiry; cost is not per lot.
- **A7. Overheads:** entered against a run and divided by good output.
- **A8. Rounding:** tax is computed per invoice line and rounded half-up to the paisa. Money is always whole paise, never floats.
- **A9. Insufficient stock:** an order can't be approved beyond available finished goods (on hand minus approved-but-not-dispatched).
- **A12. Invoice numbers:** `FF/2026-27/0001`, gapless per financial year. A cancelled invoice keeps its number and gets a credit note.
- **A15. Purchase GST:** purchase rates are tax-exclusive; input GST is recorded but not part of stock value.
- **A17. Opening date:** opening stock is dated 31 Oct 2026, so November reports show it as the opening balance.
- **Unit conversion:** each item is stored in one base unit (g, ml, pcs, pkt). kg, L and carton (= 20 packets) are conversions.

## Known gaps

- BOMs are still created through the API and the seed only — the admin UI edits items, customers and suppliers, not recipes.
- Stock cover is checked at approval (with the exact shortage). It isn't previewed in the order list before you click.
- A production run that is started but never completed leaves its materials issued, with no work-in-progress report and no run reversal yet (invoice cancellation already has one, via `inventory.post_reversals()`).
- The offline queue covers orders only, not payments. The service-worker shell keeps the app usable offline; new orders queue in localStorage.

## Repository map

| Path | What |
|---|---|
| `backend/app/<module>/` | `models`, `schemas`, `service` (rules + transactions), `router` (thin HTTP) |
| `backend/app/core/` | pure maths: money, units, GST, weighted average cost, variance |
| `backend/app/inventory/` | the stock ledger; the only code allowed to write stock movements |
| `backend/alembic/versions/` | schema migrations, including the append-only triggers |
| `backend/tests/` | unit, integration, `benchmark/` (section 5), `audit/` (hostile tests) |
| `frontend/src/` | pages per role, one API client, the offline order queue |
| `docs/` | spec, architecture, [design note](docs/design_note.md), [demo script](docs/demo_script.md), status |
