# FactoryFlow

An order-to-audit prototype for a small packaged-snack manufacturer. Every transaction is entered once at its source — salesman's phone, production floor, billing desk — and flows automatically into stock, costing, GST invoicing and the monthly auditor's reports.

Built for the NIT Tiruchirappalli Centre for Digital Infrastructure internship shortlisting task.

**Live demo:** https://factoryflow-icdx.onrender.com
*(Free tier — first load after 15 minutes idle takes about 60 seconds.)*

---

## Quick start

### Live site

Use the credentials in the [Test logins](#test-logins) section below. No setup required.

### Run locally

Prerequisites: Docker Desktop (Compose v2), Node 20+.

```bash
git clone https://github.com/preethi7711/factoryflow.git
cd factoryflow
cp .env.example .env
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed
cd frontend && npm install && npm run dev
```

API and OpenAPI docs: http://localhost:8000/docs
Web app: http://localhost:5173

To run the exact image Render deploys (migrates and seeds on start):

```bash
docker build -t factoryflow .
docker run -e DATABASE_URL=... -e SEED_ON_START=1 -p 8000:8000 factoryflow
```

---

## Test logins

Password for all accounts: **`factoryflow-demo`** (live site) or `SEED_DEMO_PASSWORD` from your `.env` locally.

| Username | Role | Access |
|---|---|---|
| `salesman_a` | Salesman | Mobile order screen; assigned to Retailer A (Tamil Nadu) |
| `salesman_b` | Salesman | Mobile order screen; assigned to Distributor B (Karnataka) |
| `admin` | Admin | Order approval, GST invoicing, dispatch, payments, all reports, masters |
| `production` | Production | Purchases, production runs, variance, cost per packet |
| `accountant` | Auditor (read-only) | All reports and exports |
| `owner` | Owner (read-only) | Dashboard, all reports |

---

## Stack and rationale

| Layer | Choice | Why |
|---|---|---|
| Database | PostgreSQL 16 | `NUMERIC` exactness; row-level `FOR UPDATE` locks; DB triggers enforce the append-only ledger |
| API | FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 | Typed, auto-generates OpenAPI docs; pure-function business modules are easy to unit-test |
| Auth | PyJWT + bcrypt | Stateless; the mobile PWA holds the token; role re-read from DB on every request |
| PDF | fpdf2 + bundled DejaVu TTF | Pure-Python, no system libraries, works on a free host; the ₹ glyph needs TrueType |
| Excel / CSV | openpyxl + stdlib `csv` | No heavy dependency for a simple export |
| Frontend | React + Vite + Tailwind (plain JS) + React Router | Thin; all business rules stay in Python/SQL where they are testable |
| Offline queue | localStorage + `Idempotency-Key` | ~60 lines, fully explainable; server-side key replay means a retry can never duplicate an order |
| Tests | pytest against real Postgres | Same SQL semantics as production; mocks would hide trigger and NUMERIC behaviour |
| Hosting | Render Free web service + Neon Free Postgres | Permanently free, no credit card; one container, one URL, no CORS |

One deployable: in production FastAPI serves the built React files, so there is a single Render service and a single Neon database.

---

## Features built (section 6 tiers)

### Must-have — all complete

| Requirement | Implementation |
|---|---|
| Login with at least 3 roles, deny by default | 5 roles (salesman, admin, production, auditor, owner); every route declares `require_roles()`; a test fails if any route omits it |
| Product, customer, raw-material and BOM masters | Full CRUD via API; admin edit/deactivate UI at `/masters` |
| Mobile-friendly order entry and admin approval | Salesman screen ≤ max-width 512 px, touch-sized buttons; approval queue with real-time stock cover check |
| GST invoice as PDF | GSTIN, HSN, CGST+SGST (intra-state) or IGST (inter-state) by place of supply; `FF/YYYY-YY/NNNN` gapless per financial year; fpdf2 |
| Production run updates stock automatically | One transaction: ISSUE raw materials, post OUTPUT finished goods, all via the append-only ledger |
| Planned vs actual consumption and yield, variance | BOM × batches = plan; actual = `−SUM(ISSUE)` from the ledger (the run and the ledger cannot disagree); flagged when `|actual − plan| / plan > tolerance` strictly |
| Stock summary and stock ledger | Opening + receipts − issues ± adjustments = closing, computed from `SUM(stock_movement)` by period; every row links to its source document |
| Sales register and stock report, CSV / Excel export | All 11 reports share one `{columns, rows, totals}` envelope; CSV (stdlib) and XLSX (openpyxl) from the same data |

### Should-have — all complete

| Requirement | Implementation |
|---|---|
| Purchases and supplier records | Full purchase flow + purchase register report |
| Payments, outstanding and ageing | Receipts allocated to invoices in one transaction; outstanding = `invoice total − SUM(allocations)` (derived, never stored); 0-30 / 31-60 / 61-90 / 91+ day ageing |
| Cost per packet with overheads | Materials issued (at WAC) + run overheads ÷ good output; ₹31.14 for the benchmark run |
| GST summary report | `/reports/gst-summary` (GSTR-3B 3.1a shape) and `/reports/hsn-summary` (GSTR-1 table 12 shape) |
| Variance alerts beyond a tolerance | `/reports/variance-alerts`: all flagged yield and material lines across completed runs for the period |
| Owner dashboard | `/dashboard`: FG stock value, pending orders, sales / collections / outstanding, completed runs, variance banner |

### Stretch — completed

| Item | Notes |
|---|---|
| Offline order capture with sync | localStorage queue per salesman; `Idempotency-Key` header; server replays on retry, 409 on body mismatch |
| Batch and expiry tracking | Every movement carries a lot number, manufacture date and expiry; FIFO allocation; FEFO is a one-line toggle (sort key change in `inventory.allocate`) |
| Tally-compatible export | `/reports/tally-daybook`: Sales / Purchase / Receipt vouchers, DD-MM-YYYY dates, paise amounts — shaped for Tally CSV import |
| Tamil / English bilingual UI | Language toggle (த / EN) in the navbar; all key labels switch at runtime; preference saved to `localStorage`; Hind Madurai font supports Tamil script natively |
| Service-worker PWA shell | `vite-plugin-pwa`: app opens offline, installable on Android/iOS; `/api` excluded from cache |
| Masters admin UI | Items, customers and suppliers: inline edit and deactivate/reactivate; every edit is audit-logged |
| Payments idempotency | `POST /payments` requires `Idempotency-Key`; replay guard closes the double-receipt window |

---

## Benchmark results (section 5 scenario)

All numbers match. The benchmark test (`backend/tests/benchmark/test_section5.py`) drives the live HTTP API as each role, runs all nine steps in order, and asserts every figure. `pytest -m benchmark` is fully green (19 checks).

| Check | Expected | Result |
|---|---|---|
| Flour closing balance | 120 kg | **120 kg** (100 + 60 − 40) |
| Oil closing balance | 19.5 L | **19.5 L** (30 − 10.5) |
| Pouches closing balance | 306 pcs | **306** (500 − 188 used − 6 damaged) |
| Finished goods after run | 238 packets | **238** (50 + 188) |
| Finished goods after Retailer A dispatch | 88 packets | **88** (238 − 150) |
| Yield variance | −6%, flagged | **−6.00%, flagged** |
| Oil consumption variance | +5%, flagged | **+5.00%, flagged** |
| Pouch variance | −3.00%, not flagged | **−3.00%, not flagged** (exactly at the boundary; tolerance is strictly greater than 3%) |
| Retailer A invoice | ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875 | **same**, invoice no. `FF/2026-27/0001` |
| Retailer A outstanding after ₹4,000 payment | ₹3,875 | **₹3,875** |
| Distributor B: insufficient stock | shortage of 32 flagged | **approval refused**: requested 120, available 88, shortage 32; IGST tax preview = ₹300, total ₹6,300 |
| Cost per packet | stated method required | **₹31.14**, margin ₹18.86 (37.7% at ₹50) |

### Cost per packet explained (₹31.14)

Valuation method: **moving weighted average cost** per item. Overheads charged to the run, divided by good output.

| Component | Calculation | Amount |
|---|---|---|
| Flour 40 kg | WAC after purchase = (100 × ₹42 + 60 × ₹45) ÷ 160 = ₹43.125/kg | ₹1,725.00 |
| Oil 10.5 L | 10.5 × ₹140 | ₹1,470.00 |
| Spice mix 1.2 kg | 1.2 × ₹200 | ₹240.00 |
| Pouches 194 pcs | 194 × ₹2.50 (6 damaged = normal run loss) | ₹485.00 |
| Cartons 9 pcs | 9 × ₹15 | ₹135.00 |
| **Materials** | | **₹4,055.00** |
| Labour | entered against run | ₹1,200.00 |
| Gas / power | entered against run | ₹600.00 |
| **Total run cost** | | **₹5,855.00** |
| **÷ 188 good packets** | | **₹31.14 / packet** |

---

## Assumptions

Documented assumptions are part of the evaluation. Full table: [docs/project_spec.md §5](docs/project_spec.md#5-assumptions-and-ambiguities-to-copy-into-the-readme).

| ID | Assumption |
|---|---|
| A1 | Variance basis: planned = BOM qty × batches; variance % = (actual − planned) / planned |
| A2 | Flag when \|variance\| is **strictly greater than** the configured tolerance (default 3%) |
| A3 | Pouch variance = 194 used vs 200 standard = −3.00% → **not flagged** (at the boundary, not beyond it) |
| A4 | Carton usage: 188 packets = 9 full cartons + 8 loose; 9 vs 10 standard = −10% flagged |
| A5 | Opening finished goods valued at standard material cost at opening rates: ₹19.85 / packet. Does not affect ₹31.14 |
| A6 | **Weighted average cost (WAC)**, moving, recomputed on each receipt. Lots are for traceability; cost is per item, not per lot |
| A7 | Overheads entered per run, divided by good output. No monthly overhead allocation for the benchmark |
| A8 | Tax computed per invoice line, rounded half-up to the paisa. Money is always integer paise, never floats |
| A9 | An order cannot be approved beyond available finished goods (on hand minus approved-but-not-dispatched) |
| A12 | Invoice numbering: `FF/YYYY-YY/NNNN`, gapless per financial year. A cancelled invoice keeps its number and receives a credit note |
| A15 | Purchase rates are tax-exclusive; input GST is recorded on the purchase line but excluded from stock value |
| A17 | Opening stock is dated 31 Oct 2026 so November reports show it as the opening balance |

---

## Known gaps

| Gap | Note |
|---|---|
| BOM edit in the UI | BOMs are created through the API and seed only. The `/masters` admin screen edits items, customers and suppliers, not recipes |
| Stock cover preview | Stock cover is checked at the moment of approval (exact shortage shown). It is not displayed in the order list before the admin clicks Approve |
| Run reversal | A production run that is started but never completed leaves its materials issued with no reversal mechanism. Invoice cancellation has one (`inventory.post_reversals()`); the same primitive would handle runs |
| Offline payments | The offline queue covers orders only. Payments require a live connection |

---

## Technical design

The full design — ER diagram, stock ledger model, WAC computation, GST logic, invariant enforcement — is in [docs/design_note.md](docs/design_note.md).

### Key invariants and how they are enforced

| Invariant | Mechanism | Verified by |
|---|---|---|
| Stock is derived from the ledger, never overwritten | Balances are `SUM(qty)` and `SUM(value_paise)` queries; no writable balance column | `test_ledger_reconciles_after_every_step` |
| Ledger is append-only | DB trigger raises on `UPDATE` / `DELETE` / `TRUNCATE` of `stock_movement` | `test_ledger_and_audit_log_are_append_only` |
| Every movement links to a source document | `source_type + source_id + source_line_id NOT NULL`; composite lot/item FK | `test_database_rejects_bad_movements` |
| No negative stock | Item rows locked `FOR UPDATE`; balance checked in the same transaction as the outflow | Concurrency and audit tests |
| Exact money | Integer paise; `Decimal` quantities; half-up rounding at named points only | Unit tests for `money`, `gst`, `wac` |
| Posted documents are immutable | State machine; cancellation = credit note + REVERSAL movements | Billing tests |
| Audit trail | `audit.record()` in the same transaction as every edit | Audit tests |
| Role access | `require_roles()` on every route; role re-read from DB, not from the token | `test_every_route_declares_its_roles` |

### Repository layout

```
backend/app/<module>/   models · schemas · service (rules + txns) · router (thin HTTP)
backend/app/core/       pure maths: money · units · GST · WAC · variance
backend/app/inventory/  stock_movement ledger — the only code that writes stock
backend/alembic/        schema migrations, including the append-only triggers
backend/tests/          unit · integration · benchmark/ (section 5) · audit/ (hostile tests)
frontend/src/           pages per role · API client · offline order queue · i18n
docs/                   project_spec · architecture · design_note · demo_script
```

---

## Running the tests

```bash
# Full backend suite (338 tests)
docker compose exec api pytest

# Section 5 benchmark only (19 checks, all green)
docker compose exec api pytest -m benchmark -v

# Lint
docker compose exec api sh -c "ruff check . && ruff format --check ."

# Frontend (money helpers + offline queue)
cd frontend && npm run test && npm run lint
```
