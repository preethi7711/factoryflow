# Architecture: FactoryFlow

*How* the system works. *What* it must do: [project_spec.md](project_spec.md). Build order: [roadmap.md](roadmap.md).

## 1. Shape: modular monolith, one deployable

```
Browser (React PWA, plain JS) ──/api/v1 JSON──> FastAPI ──SQLAlchemy 2──> PostgreSQL 16
            ▲                                       │
            └──── built static files served by ─────┘   (prod: one container, one URL, no CORS)
```

Backend modules (`backend/app/<module>/{models,schemas,service,router}.py`):

| Module | Owns |
|---|---|
| `core` | config, db session, security, **pure maths**: `money`, `units`, `gst`, `wac`, `variance` |
| `auth` | users, roles, JWT, `require_roles()` |
| `masters` | items, units, BOM, customers, suppliers, price list, company settings |
| `inventory` | **`stock_movement` ledger**, lots, `post_movements()`, `allocate()`, balances, reconcile |
| `production` | runs, consumption, overheads, variance, cost per packet |
| `purchasing` | purchases (receipts) |
| `sales` | orders (idempotent), approval, stock check, dispatch |
| `billing` | invoices, FY numbering, credit notes, PDF |
| `payments` | receipts, allocation, outstanding, ageing |
| `reports` | registers, GST summary, stock and production reports, CSV/XLSX |
| `audit` | `audit_log`, `record()` |

Rules: routers stay thin (parse, authorise, call the service). Services own transactions. Only `inventory.service`
writes `stock_movement`. Modules call each other's **services**, never each other's tables.
**Why not microservices:** one factory and about 20 users, and stock must change in the same DB transaction as the
invoice or run that causes it.

## 2. Tech stack

| Layer | Choice | Rejected (why) |
|---|---|---|
| DB | PostgreSQL 16 | SQLite: weak NUMERIC, no `SELECT … FOR UPDATE` |
| API | FastAPI, SQLAlchemy 2 (sync, psycopg 3), Alembic, Pydantic v2 + pydantic-settings | Django: more framework magic to explain live; async SQLAlchemy: harder to debug for ~20 users |
| Auth | PyJWT + `bcrypt` | passlib: unmaintained |
| PDF | fpdf2 + bundled DejaVu TTF (₹ glyph) | WeasyPrint: needs Pango/Cairo system libs |
| Export | openpyxl + stdlib `csv` | pandas: heavy for simple exports |
| Web | React + Vite + Tailwind (JS), React Router, `fetch`, `vite-plugin-pwa` | Next.js: SSR we don't need |
| Offline | localStorage queue + `Idempotency-Key` | Workbox Background Sync: opaque, uneven browser support |
| Tests | pytest on real Postgres (separate test DB) | SQLite or mocks: hide trigger and NUMERIC behaviour |
| Lint | ruff; ESLint + Prettier | black + flake8 + isort |
| Ops | Docker Compose; GitHub Actions | none |

**Hosting** (free, no card, verified 2026-11-23):
- **Render Free web service** (Docker, auto-deploy from `main`). Spins down after 15 min idle, about 1 min cold start, 750 h/month, no persistent disk, so PDFs are generated on request.
- **Neon Free Postgres**: permanent, no card, 1 GB/project, 100 CU-h/month, scale-to-zero after 5 min. **No keep-alive pings**, because they would burn the compute hours.
- Rejected: Render Free Postgres, which is deleted 30 days after creation.

## 3. Data model

Conventions:
- `*_paise BIGINT`; `*_qty NUMERIC(18,3)` in the item **base unit**; `*_bp INT` basis points (500 = 5%).
- Every document has `status` and `created_by/at`.

```mermaid
erDiagram
  app_user ||--o{ sales_order : "salesman places"
  item ||--o{ item_unit : "pack units (carton = 20 pkt)"
  item ||--o{ stock_lot : "batches + expiry"
  item ||--o{ stock_movement : ""
  stock_lot ||--o{ stock_movement : ""
  item ||--o{ bom : "FG item"
  bom ||--|{ bom_line : "ingredients + packaging per batch"
  bom ||--o{ production_run : ""
  production_run ||--|{ run_consumption : "planned vs actual"
  production_run ||--o{ run_overhead : "labour, gas/power"
  supplier ||--o{ purchase : ""
  purchase ||--|{ purchase_line : ""
  customer ||--o{ sales_order : ""
  sales_order ||--|{ order_line : ""
  sales_order ||--o| invoice : ""
  invoice ||--|{ invoice_line : ""
  invoice ||--o{ dispatch : ""
  invoice ||--o| credit_note : "cancellation"
  customer ||--o{ payment : ""
  payment ||--|{ payment_allocation : ""
  invoice ||--o{ payment_allocation : ""
  app_user ||--o{ audit_log : "who"
```

**`stock_movement`** (the ledger):
- Columns: `item_id`, `lot_id` NOT NULL, signed `qty`, signed `value_paise`, `movement_type` (OPENING, PURCHASE, ISSUE, OUTPUT, SCRAP, DISPATCH, ADJUST, COST_ADJUST, REVERSAL), `source_type` + `source_id` + `source_line_id` NOT NULL, `reverses_id`, `posted_at`, `posted_by`.
- Balance and value = `SUM(qty)` and `SUM(value_paise)` by item or lot. **There is no balance column.**

Other key fields:
- **`item`**: `kind` RAW|PACKAGING|FG, `base_uom`, `hsn`, `gst_rate_bp`, `sale_price_paise`, `variance_tol_bp` (default 300), `shelf_life_days`.
- **`stock_lot`**: `lot_no`, `mfg_date`, `expiry_date`, `received_at`, source. Created by an opening, a purchase line or a run output.
- **`invoice`**: `fy`, `seq`, `invoice_no` `FF/2026-27/0001`, `place_of_supply_state`, `supply_type` INTRA|INTER, totals.
  `invoice_sequence(fy, last_seq)` is row-locked, so numbering is gapless.
- **`idempotency_key`**: key, user, route, request hash, stored response. **`audit_log`**: entity, id, action, before/after `jsonb`, user, time.

## 4. Invariants: how each is enforced

| Invariant | Mechanism | Proven by |
|---|---|---|
| Stock derived from ledger | balances are `SUM()` queries; no writable balance | `test_ledger_reconciles` |
| Append-only ledger | DB trigger raises on UPDATE/DELETE of `stock_movement` | trigger test |
| Traceability | `source_*` NOT NULL | `test_every_movement_has_source` |
| No negative stock | item rows locked `FOR UPDATE`, balance checked in the same txn | concurrency test |
| Exact money and quantities | `int` paise, `Decimal` qty, half-up rounding at named points only | unit tests |
| Posted docs immutable | state machine; cancel = credit note + REVERSAL movements | billing tests |
| Audit | `audit.record()` in the same txn as the change | audit tests |
| Role access | `require_roles()` on every route, deny by default | RBAC tests |

## 5. The hard parts

- **Units:**
  - Global units: `g`, `kg = 1000 g`, `ml`, `l = 1000 ml`, `pcs`, `pkt`.
  - Item-specific packs live in `item_unit` (Murukku: `carton = 20 pkt`).
  - `to_base()` multiplies with Decimal, which is exact. Converting across dimensions is an error.
- **WAC (moving weighted average):**
  - Receipt value = qty × rate.
  - Issue value = `round_half_up(qty × Σvalue / Σqty)`.
  - **Anti-drift:** an issue that empties an item takes all of the remaining value.
  - Lots exist for traceability only; cost is WAC per item.
- **Production post (one txn):**
  1. Lock the items and check stock.
  2. Post ISSUE movements for the actual quantities (pouches 194 = 188 good + 6 damaged).
  3. Create the FG lot `RUN-0001` with expiry = run date + shelf life.
  4. Post OUTPUT +188, valued at material cost.
  5. Audit.
- **Overheads added later** post a `COST_ADJUST` movement (qty 0, value > 0) on the run's FG lot. Append-only, and FG value stays right.
- **Cost per packet** = (materials + run overheads) / good output.
- **Variance:**
  - Planned = BOM qty × batches. `var_bp = (actual − planned) × 10000 / planned`, half-up, for display.
  - Flag when `|actual − planned| × 10000 > tol_bp × planned`: the exact value, not the rounded bp, so 3.004%
    is still flagged. Yield variance is computed the same way on output.
- **Rounding points (the only places we round, all half-up to the paisa):** receipt line value
  (`wac.receipt_value`), issue value (`wac.issue_value`, except an emptying issue), each tax component per line
  (`gst.line_tax`), cost per unit (`wac.cost_per_unit_paise`). Variance bp is rounded for display only.
- **GST:**
  - Company state 33 (TN). Place of supply = customer state.
  - Intra-state: CGST = SGST = `half_up(taxable × bp/2 / 10000)` per line.
  - Inter-state: IGST = `half_up(taxable × bp / 10000)`.
  - FY runs April–March.
- **Stock check:**
  - available = FG on hand − approved-but-undispatched qty.
  - Over-approval returns `INSUFFICIENT_STOCK` with requested, available, shortage and batches needed.
  - Admin can approve a partial quantity or hold the order.
- **Lot allocation:** `inventory.allocate()` draws lots FIFO by `received_at`. FEFO = change the sort key to `expiry_date` (stretch toggle).
- **Offline orders:**
  - The PWA queues each order in localStorage with `client_uuid = crypto.randomUUID()` and sends it as the `Idempotency-Key`.
  - Server: same key + same body hash → replay the stored response. Same key + different body → 409. `sales_order.client_uuid` is UNIQUE.
  - The server re-prices from the price list.
