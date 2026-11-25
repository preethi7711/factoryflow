# FactoryFlow: Project Architecture & Mastery Blueprint

> **Purpose:** An independent guide for understanding, explaining, debugging, and extending FactoryFlow —
> written from a thorough inspection of the actual implemented code, not from theory or plans.

---

## 1. System Architecture

### 1.1 The Big Picture

```
Browser (React 18 SPA, plain JS)
   │  fetch JSON over /api/v1
   ▼
FastAPI (Python 3.12)   ─── serves the built React files at "/"
   │  SQLAlchemy 2 (sync, psycopg 3)
   ▼
PostgreSQL 16 (Neon Free on production; Docker Compose locally)
```

**One deployable, one URL.** The root `Dockerfile` builds the React app, then copies the
static bundle into the Python image. FastAPI serves `/api/v1/*` for the API and falls through to
the static files for everything else (`app/core/spa.py`). In development, Vite runs on :5173 and
proxies `/api` to :8000.

### 1.2 Module Map (backend)

```
backend/app/
├── main.py          ← FastAPI app: mounts all routers under /api/v1
├── models.py        ← one-line file: imports every model so SQLAlchemy sees all tables
├── seed.py          ← creates demo users, master data, and opening stock
├── core/            ← pure maths + config + db + security (no HTTP, no database in core/)
│   ├── money.py     ← integer paise, round_half_up, format_inr
│   ├── units.py     ← to_base(), from_base(), global units (g kg ml l pcs pkt)
│   ├── gst.py       ← INTRA/INTER supply type, line_tax(), invoice_no(), financial_year()
│   ├── wac.py       ← receipt_value(), issue_value(), cost_per_unit_paise(), Balance dataclass
│   ├── variance.py  ← planned_qty(), variance(), flag when |diff| × 10000 > tol × planned
│   ├── config.py    ← pydantic-settings; refuses weak JWT_SECRET_KEY in production
│   ├── db.py        ← engine, SessionLocal, get_db dependency, Base, QTY type
│   ├── security.py  ← JWT encode/decode, bcrypt hashing
│   └── errors.py    ← AppError (raises JSON {"error":{code,message,details}})
├── auth/            ← users, roles (salesman admin production auditor owner), JWT
├── masters/         ← items, units, BOM, customers, suppliers, price list
├── inventory/       ← THE HEART: stock_movement, lots, post_movements(), allocate(), balance()
├── production/      ← runs, consumption, overheads, variance, cost
├── purchasing/      ← purchases, receipts
├── sales/           ← orders (idempotent), approval, stock check
├── billing/         ← invoices, dispatch, credit notes, PDF
├── payments/        ← payments, allocation, outstanding
├── reports/         ← read-only: sales register, stock summary/ledger, production, CSV/XLSX
└── audit/           ← append-only audit_log (who, when, before→after JSON)
```

### 1.3 Key Invariants (non-negotiable)

| Invariant | Where enforced |
|---|---|
| Stock = SUM(ledger), never stored | `inventory/service.py:balance()` |
| Ledger is append-only | DB trigger blocks UPDATE/DELETE on `stock_movement` |
| Every movement links to a source document | `source_type` + `source_id` NOT NULL; `_require_source_exists()` |
| Money = integer paise, never float | `core/money.py`; float inputs raise `TypeError` |
| Quantities = exact Decimal in base units | `core/units.py:parse_qty()`; float inputs refused |
| Posted docs are never deleted | State machine; credit notes + REVERSAL movements |
| No negative stock | Item rows locked (`FOR UPDATE`) before each outflow |

### 1.4 Data Flow: Order → Dispatch (the main path)

```
Salesman (phone)                   Admin                    Production floor
     │                               │                            │
1. queue.enqueue(body)         4. approve_order()           2. start_run() — ISSUEs raw stock
     │ Idempotency-Key               │ lock items, check available │
2. POST /orders  ─────────────────► │ APPROVED                   3. complete_run() — ISSUEs
   server re-prices from list        │                               packaging, creates FG lot
   stores IdempotencyKey row         │                               posts OUTPUT (+FG, valued
     │                         5. invoice(order_id)          at material cost)
     │                               │ gapless seq via row lock    │
     │                               │ CGST+SGST or IGST          8. add_overheads()
     │                         6. dispatch(invoice_id)             │ COST_ADJUST on FG lot
     │                               │ DISPATCH movement(s)        │ (value only, qty 0)
     │                               │ lot allocated FIFO
     │                         7. payment(customer_id, amount)
     │                               │ allocates to invoice
     │                               │ outstanding = derived SUM
     ▼
 localStorage queue   ◄──────────────── synced / failed / pending
```

---

## 2. Technology Stack

| Layer | Choice | Why this, not X |
|---|---|---|
| DB | PostgreSQL 16 | Exact NUMERIC; triggers; row-level locks; jsonb audit |
| ORM | SQLAlchemy 2 (sync) | Explicit, debuggable; async is overkill for 20 users |
| Migrations | Alembic | Version-controlled schema; rolls forward on container start |
| API | FastAPI | Auto-generated docs; type-checked Pydantic schemas; dependency injection |
| Validation | Pydantic v2 | Strict types at the API boundary; model serialization |
| Auth | PyJWT + bcrypt | Stateless JWT; role read from DB on every request (not from token) |
| PDF | fpdf2 + DejaVu TTF | Pure Python; no system libs; ₹ glyph works |
| Excel/CSV | openpyxl + stdlib csv | Lightweight; no pandas needed for simple exports |
| Frontend | React 18 + Vite 5 | Thin SPA; no SSR needed |
| Styling | Tailwind CSS 3 | Utility-first; design tokens in `tailwind.config.js` |
| Offline | localStorage queue + Idempotency-Key | 50 lines, fully testable, no service worker |
| Tests (backend) | pytest + real Postgres | Same SQL semantics as production; triggers actually fire |
| Tests (frontend) | vitest | Fast; runs in Node; no browser needed |
| Lint | ruff (Python), ESLint + Prettier (JS) | One fast tool per language |
| CI | GitHub Actions (public repo = free) | Tests pass on every push to main |
| Hosting | Render Free (Docker) + Neon Free Postgres | No credit card; Neon is permanent |

---

## 3. Prerequisite Learning Roadmap

Learn these in order. Each section gives the depth you need and what to skip.

### Stage 1 — Python Foundations (if you're new to Python)
- Variables, strings, lists, dicts, f-strings
- Functions, `*args`, `**kwargs`, type hints (`def foo(x: int) -> str`)
- Classes, `__init__`, dataclasses
- `Decimal` from the `decimal` module — **why not float** is the single most important concept
- Exceptions: `try/except/raise`, custom exception classes
- **Skip:** async/await (this project uses sync), metaclasses, descriptors

**Free resource:** https://docs.python.org/3/tutorial/ (Chapters 3–9 only)
**Time:** 8–12 h if you know another language

### Stage 2 — HTTP and REST (1–2 h)
- HTTP verbs: GET, POST, PUT, DELETE, PATCH
- Status codes: 200, 201, 401, 403, 404, 409, 422
- Headers: `Authorization: Bearer <token>`, `Content-Type: application/json`
- JSON: how Python dicts map to JSON objects
- **Skip:** WebSockets, HTTP/2, caching headers

### Stage 3 — FastAPI (3–4 h)
- Creating an app, `@app.get`, `@app.post`
- Path parameters `/items/{id}`, query parameters `?from=...`
- Request body with Pydantic models
- Dependency injection: `Depends(get_db)`, `Depends(require_roles(...))`
- Error handling: `HTTPException` and custom handlers
- **Skip:** background tasks, WebSocket routes, `APIRouter` (you'll learn from reading the code)

**Free resource:** https://fastapi.tiangolo.com/tutorial/ (up to "Dependencies")
**Time:** 3–4 h

### Stage 4 — SQLAlchemy 2 (ORM style, 4–5 h)
- `DeclarativeBase`, `mapped_column`, `Mapped[T]`
- Session: `db.add()`, `db.flush()`, `db.commit()`, `db.rollback()`
- Queries: `select(Model).where(...)`, `db.scalar()`, `db.scalars()`
- `func.sum()`, `func.coalesce()`, `group_by()`, `having()`
- `with_for_update()` — row-level locking (critical for understanding stock checks)
- Relationships: `relationship()`, lazy vs eager loading
- **Skip:** async session, ORM events, hybrid properties

**Free resource:** https://docs.sqlalchemy.org/en/20/orm/quickstart.html
**Time:** 4–5 h

### Stage 5 — Alembic (1 h)
- `alembic revision --autogenerate -m "..."` to create a migration
- `alembic upgrade head` to apply
- How `env.py` connects to the models

### Stage 6 — React (if you know HTML/CSS/JS, 4–6 h)
- Components as functions, JSX syntax
- `useState`, `useEffect`, `useCallback`, `useMemo`
- Props and how data flows down
- Context API: `createContext`, `useContext`, `Provider`
- React Router: `<Route>`, `<Navigate>`, `useNavigate`, `NavLink`
- **Skip:** class components, Redux, Next.js, TypeScript generics

**Free resource:** https://react.dev/learn (Describing the UI + Adding Interactivity sections)
**Time:** 4–6 h

### Stage 7 — Tailwind CSS (1–2 h)
- Utility classes: padding (`p-4`), margin (`m-2`), flex, grid
- Responsive prefixes: `sm:`, `lg:`
- Custom colours via tokens (`text-choc-900`, `bg-turmeric-500` from `tailwind.config.js`)
- **Skip:** plugins, JIT deep-dives

### Stage 8 — GST (Indian) Basics (1 h, domain-specific)
- CGST + SGST for intra-state (same state): each at half the rate
- IGST for inter-state: full rate
- HSN codes identify goods
- Invoice numbering (`FF/2026-27/0001`): financial year runs April–March
- **Skip:** GSTR-3B filing, e-Way Bill (not built)

---

## 4. Codebase Exploration Roadmap

Follow this order. Read the file, then trace one function from start to finish.

### Pass 1 — Pure maths (no database, no HTTP)

| Order | File | Why first |
|---|---|---|
| 1 | `backend/app/core/money.py` | Everything money-related depends on this. Understand `round_half_up` and why floats are banned. |
| 2 | `backend/app/core/units.py` | Stock quantities live in a base unit. `to_base("10.5", "l", "ml")` returns `Decimal("10500.0")`. |
| 3 | `backend/app/core/gst.py` | CGST/SGST vs IGST; `line_tax()`; `financial_year()`; `invoice_no()`. |
| 4 | `backend/app/core/wac.py` | Moving weighted average. `receipt_value()`, `issue_value()`, anti-drift rule. |
| 5 | `backend/app/core/variance.py` | Planned vs actual; why the flag uses exact numbers, not rounded bp. |

**Checkpoint:** Read `backend/tests/unit/test_money.py`, `test_wac.py`, `test_gst.py`. Can you explain what each test proves?

### Pass 2 — Infrastructure

| Order | File | Why |
|---|---|---|
| 6 | `backend/app/core/config.py` | Settings from env; production secret check. |
| 7 | `backend/app/core/db.py` | Engine, `SessionLocal`, `get_db` dependency, `QTY` type alias. |
| 8 | `backend/app/core/security.py` | JWT encode/decode, bcrypt. |
| 9 | `backend/app/auth/deps.py` | `get_current_user`, `require_roles()` — the entire RBAC system. |
| 10 | `backend/app/core/errors.py` | `AppError` and how it becomes `{"error": {...}}` JSON. |
| 11 | `backend/app/main.py` | How routers are mounted; why the SPA mount is last. |

### Pass 3 — The Ledger (the heart of the system)

| Order | File | Why |
|---|---|---|
| 12 | `backend/app/inventory/models.py` | `StockMovement` columns; `MovementType` enum; `SourceType` enum; the sign CHECK constraint. |
| 13 | `backend/app/inventory/service.py` | `balance()`, `allocate()`, `post_movements()`, `post_reversals()`, `reconcile()`. Read every comment. |

**Checkpoint:** Trace a production run's output through `post_movements()`. Which `MovementType` is it? What is `source_type`? What value does the OUTPUT carry?

### Pass 4 — Business Modules

| Order | File | Trace this call |
|---|---|---|
| 14 | `backend/app/masters/service.py` | `get_bom()`, `lock_items()`, `base_qty()` |
| 15 | `backend/app/purchasing/service.py` | `create_purchase()` → receipt → lot → `post_movements()` |
| 16 | `backend/app/production/service.py` | `start_run()` → `complete_run()` → `add_overheads()` |
| 17 | `backend/app/sales/service.py` | `create_order()` idempotency → `approve_order()` stock check |
| 18 | `backend/app/billing/service.py` | `create_invoice()` → `dispatch()` → `cancel_invoice()` |
| 19 | `backend/app/payments/service.py` | `create_payment()` → allocation → outstanding |
| 20 | `backend/app/reports/service.py` | `stock_summary()` — opening/period/closing construction |

### Pass 5 — Frontend

| Order | File | Purpose |
|---|---|---|
| 21 | `frontend/src/api/client.js` | `api()` and `apiBlob()` — the fetch wrapper |
| 22 | `frontend/src/format.js` | `inr()`, `toPaise()`, `decMul()`, `localToday()`, `showQty()` |
| 23 | `frontend/src/auth/AuthContext.jsx` | JWT stored in localStorage; `login()` / `logout()` |
| 24 | `frontend/src/offline/queue.js` | `makeQueue()` — enqueue, flush, idempotency |
| 25 | `frontend/src/ui.jsx` | `Button`, `Card`, `Banner`, `Field`, `Pill`, `input` token |
| 26 | `frontend/src/App.jsx` | Routes; `Protected` guard; role-to-home mapping |
| 27 | `frontend/src/components/Layout.jsx` | Header; role-specific nav; width (`max-w-lg` for salesman) |
| 28 | `frontend/src/pages/LoginPage.jsx` | Login form → `AuthContext.login()` |
| 29 | `frontend/src/pages/OrderPage.jsx` | Full salesman flow; offline queue integration |
| 30 | `frontend/src/pages/AdminOrdersPage.jsx` | Approve → invoice → dispatch → payment |
| 31 | `frontend/src/pages/ProductionPage.jsx` | Start → complete → overheads; `PurchaseCard` |
| 32 | `frontend/src/pages/StockPage.jsx` | Report viewer + downloads (`apiBlob`) |

### Pass 6 — Tests

| Order | File | What it teaches |
|---|---|---|
| 33 | `backend/tests/invariants.py` | The three invariant queries run after every benchmark step |
| 34 | `backend/tests/benchmark/test_section5.py` | The whole scenario as one pytest; the contract for all expected numbers |
| 35 | `backend/tests/integration/test_ledger.py` | Append-only trigger test; WAC correctness |
| 36 | `backend/tests/audit/test_p4_ledger_audit.py` | Hostile tests: double-post, negative stock, float injection |

---

## 5. Skill-to-Code Mapping

### "Why is stock never negative?"

`inventory/service.py:post_movements()` calls `masters.lock_items()` with `SELECT … FOR UPDATE`
before inserting. It then checks the per-lot balance both as-of-date and currently
(lines 334–337). `InsufficientStockError` is raised if any check fails.

### "How is money kept exact?"

`core/money.py:round_half_up()` takes a `Decimal` and returns an `int` (paise). Every place that
produces paise calls this function. Float inputs raise `TypeError` immediately.
In the frontend, `toPaise(text)` in `format.js` parses strings via regex — never through `parseFloat`.

### "How does the idempotency key work?"

`sales/service.py:create_order()` checks `db.get(IdempotencyKey, key)` first. If found, it
calls `_replay()` which returns the stored response JSON. The order's `client_uuid` is UNIQUE in
the DB as a second guard. Concurrent double-taps: an `IntegrityError` is caught, the loser rolls
back and replays the winner (lines 194–199).

### "How is GST calculated?"

`core/gst.py:line_tax()` takes `taxable_paise`, `rate_bp` and `supply` (INTRA or INTER). For
INTRA: `half = apply_bp(taxable, rate_bp/2)` for each of CGST and SGST. For INTER: one IGST at
the full rate. Each line is rounded independently. Never computed on the invoice total.

### "How is the weighted average cost maintained?"

`core/wac.py:issue_value(qty, bal_qty, bal_value)`: if the issue empties stock, return all
remaining value (anti-drift rule). Otherwise `round_half_up(qty × bal_value / bal_qty)`.
The `Balance` dataclass in `wac.py` is for unit tests only; the real balance is always
`inventory.service.balance()` which calls `SUM(ledger)`.

### "How does a production run work in the database?"

Two calls, each one transaction:
1. `POST /production-runs` → `start_run()` → creates `ProductionRun`, `RunConsumption` rows,
   then calls `_issue()` → `post_movements()` with `MovementType.ISSUE` for each raw material.
2. `POST /production-runs/{id}/complete` → `complete_run()` → issues packaging, creates
   `StockLot` for FG (lot_no = run_no), posts `OUTPUT` with value = `SUM(ISSUE values)`.
3. `POST /production-runs/{id}/overheads` → `add_overheads()` → posts `COST_ADJUST` (qty=0,
   value=overhead amount) on the FG lot, dated on the run date.

### "How do reports reconcile?"

`reports/service.py:stock_summary()` tiles the ledger into three time windows with the same
`SUM(qty)` query as `inventory.service.balance()`. Opening = SUM where `movement_date < from`,
period = `[from, to]`. Since closing = SUM where `movement_date ≤ to`, and the period rows
include every inflow and outflow in that window, `opening + receipts − issues ± adjustments`
equals `closing` by arithmetic identity.

### "How does RBAC work?"

`auth/deps.py:require_roles(*roles)` returns a FastAPI dependency. When a route declares
`user: Annotated[AppUser, Depends(require_roles(Role.ADMIN))]`, FastAPI extracts the JWT,
re-reads the user from the DB (so a deactivated account is rejected immediately), and raises
403 if the role doesn't match. A test in `tests/integration/test_auth.py` walks every route
and fails if any forgets to declare `require_roles`.

---

## 6. End-to-End Feature Walkthroughs

### Feature A: Salesman places an order offline and it syncs

1. **UI** (`OrderPage.jsx`): User taps quantity buttons → `setCount()` updates state.
   User taps "Place order" → `placeOrder()` calls `queue.enqueue(body)`.
2. **Queue** (`offline/queue.js`): `enqueue()` generates `crypto.randomUUID()` as
   `client_uuid`, appends to localStorage as `{state: "pending", ...}`.
3. **Flush** (`queue.flush(send)`): For each pending item, calls `send(client_uuid, body)`.
   `send` calls `api("/orders", {method:"POST", body, headers: {"Idempotency-Key": client_uuid}})`.
4. **Backend** (`sales/router.py`): extracts the `Idempotency-Key` header, calls
   `sales.create_order(db, key, data, user)`.
5. **Service** (`sales/service.py`): checks for existing key → not found → creates order,
   prices from price list, stores idempotency row with response JSON, commits.
6. **Response**: `{id, status:"PENDING", ...}`. Queue item becomes `{state:"synced"}`.
7. **On retry** (network hiccup): same `client_uuid` → `_replay()` returns the first result.

### Feature B: Production run → variance flagged

1. **UI** (`ProductionPage.jsx`): Supervisor selects BOM, sets batches. `plan` is computed
   from `bom.lines` using `planLine()` and `decMul()`. Planned values fill the "Issued" column.
2. Supervisor changes oil from `10` to `10.5`, clicks "Start run":
   `issues = [{item_id: OIL_ID, qty: "10.5", uom: "l"}]`.
3. **Backend** `start_run()`: converts `10.5 l` to `10500.000 ml` via `units.to_base()`. Posts
   ISSUE movement of -10500 ml valued at WAC.
4. Supervisor records output 188, packaging 194 pouches, 6 damaged, 9 cartons, clicks "Complete run".
5. **Backend** `complete_run()`: issues packaging, creates FG lot, posts OUTPUT +188 pkt valued at
   the sum of all ISSUE values.
6. UI fetches `GET /production-runs/{id}/variance` → renders `VarianceBars`.
7. **Backend** `run_variance()`: for OIL, `variance(10000.000, 10500.000, 300)` →
   `diff = 500`, `bp = round_half_up(500 × 10000 / 10000) = 500`, `flag = |500| × 10000 > 300 × 10000` → `True`.

### Feature C: Invoice and GST calculation

1. Admin clicks "Raise invoice" on an APPROVED order.
2. **Backend** `billing/service.py:create_invoice()`:
   - Locks `invoice_sequence(fy)` row with `FOR UPDATE`, increments seq (gapless).
   - Calls `gst.supply_type("33", customer.state_code)` → INTRA (TN→TN) or INTER (TN→KA).
   - For each line: `line_tax(taxable, rate_bp, supply)` → `LineTax(taxable, cgst, sgst, igst)`.
   - Sums all lines → invoice totals.
   - Invoice gets `invoice_no = "FF/2026-27/0001"`.
3. **Frontend** `AdminOrdersPage.jsx:taxLine(inv)` formats: "₹7,500.00 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875.00".

---

## 7. Practical Mastery Exercises

Work through these in order. Each one is a complete round-trip.

### Exercise 1 — Understand WAC (45 min)
**Task:** Open `backend/tests/unit/test_wac.py`. Run one test with `pytest tests/unit/test_wac.py -v`.
**Question:** What does the anti-drift rule prevent? What would happen without it?
**Extend:** Add a test: receipt 100 g at 50 paise/g, issue all 100 g. Assert `issue_value == 5000`
(the whole value, not `round_half_up(100 × 5000 / 100)`).

### Exercise 2 — Trace a purchase (1 h)
**Task:** Open `backend/app/purchasing/service.py`. Find `create_purchase()`. Draw the call chain:
service → `inventory.post_movements()` → what does `MovementLine` look like for a purchase?
**Question:** What is `source_type` for a purchase movement? What is `source_line_id`?
**Extend:** Add a purchase line for a second item in the same call and check the test still passes.

### Exercise 3 — Break and fix RBAC (30 min)
**Task:** In `backend/app/sales/router.py`, temporarily remove `Depends(require_roles(Role.SALESMAN))`
from the order-creation route. Run `pytest tests/integration/test_auth.py -v`. See it fail.
Restore it. See it pass. This is the route-policy guard.

### Exercise 4 — Follow the ledger (1 h)
**Task:** After seeding, run the benchmark locally: `docker compose run --rm api pytest -m benchmark -v`.
**Question:** After step 2 (production run), what does `GET /stock/balance?item_code=FLOUR` return?
How did it change from step 0 (opening 100 kg)?
**Extend:** Add a `print()` inside `inventory.service.post_movements()` that logs every inserted row,
run step 2, observe what gets posted.

### Exercise 5 — Extend the production screen (1 h)
**Task (from docs/interview_notes.md):** Show the profit margin on the production screen. The margin
is `sale_price_paise − cost_per_unit_paise`. Both are already in the response from
`GET /production-runs/{id}/cost` and `GET /items/{id}`.
**Where:** `ProductionPage.jsx`, inside the `CostBreakdown` component imported from `RunVisuals.jsx`.
**Check:** The number should be ₹18.86 for the benchmark run.

### Exercise 6 — Add a new report column (45 min)
**Task:** Add a "customer_name" column to the sales register.
**Where:** `backend/app/reports/service.py:sales_register()`. The `customer` object is already fetched.
Add `"customer_name": customer.name` to each row dict, and add a `Column` entry in `_cols(...)`.
**Check:** `GET /reports/sales-register?from=2026-11-01&to=2026-11-30` returns the new column.

### Exercise 7 — Write a new unit test (30 min)
**Task:** Write a test in `backend/tests/unit/test_gst.py` for the case where `taxable = 10001` paise
and `rate_bp = 500` INTER. What should `igst_paise` equal? Use `apply_bp(10001, 500)` to verify.

### Exercise 8 — Debug a 500 locally (1 h)
**Task:** Simulate the stale-migration bug from project history. Run `docker compose up` without
running `alembic upgrade head`. Try to POST a purchase. See the 500. Run the migration and retry.
**Lesson:** Why the dev Dockerfile doesn't auto-migrate but the production image does.

---

## 8. Learning Schedule (Realistic, ~12 h total)

### Session 1 (2–3 h): Foundations
- Read `core/money.py`, `core/units.py`, `core/gst.py`
- Run `pytest tests/unit/ -v` and read every test
- Do Exercises 1 and 7
- **Checkpoint:** Can you explain why `0.1 + 0.2 ≠ 0.3` in Python floats and how `Decimal` fixes it?

### Session 2 (2–3 h): The Ledger
- Read `inventory/models.py` and `inventory/service.py`
- Read `core/wac.py` alongside `production/service.py` (complete_run)
- Do Exercise 4 (trace ledger)
- **Checkpoint:** Can you explain what happens inside `post_movements()` for an outflow that spans two lots?

### Session 3 (2 h): The API and RBAC
- Read `main.py`, `auth/deps.py`, `core/errors.py`
- Read `sales/service.py` (focus on `create_order` idempotency)
- Do Exercise 3 (RBAC break/fix)
- **Checkpoint:** How does `require_roles` work as a FastAPI dependency? What does `dependency.allowed_roles` do?

### Session 4 (2 h): Frontend
- Read `api/client.js`, `format.js`, `auth/AuthContext.jsx`
- Read `offline/queue.js` and `queue.test.js`
- Do Exercise 5 (margin on production screen)
- **Checkpoint:** How does the salesman's order survive a network outage and sync when back online?

### Session 5 (2 h): End-to-End Scenario
- Drive the entire benchmark manually in a browser (see `docs/demo_script.md`)
- Do Exercise 6 (new report column)
- Read `tests/benchmark/test_section5.py` from top to bottom
- **Checkpoint:** Can you re-run `pytest -m benchmark -v` and explain what each assertion checks?

---

## 9. Interview Preparation

### Architectural Questions

**Q: Why a modular monolith instead of microservices?**
> Stock must change in the same DB transaction as the invoice or run that caused it. With
> microservices, that becomes a distributed transaction (two-phase commit or saga pattern),
> which adds complexity without benefit for a 20-user factory. One transaction = one ACID guarantee.

**Q: Why is the stock balance not stored as a column somewhere?**
> A stored balance can drift if any bug skips updating it. A `SUM(ledger)` is always exact because
> it derives from the same rows the application writes. The DB trigger makes the ledger append-only,
> so the balance can't be tampered with. A test (`test_ledger_reconciles_after_every_step`) proves
> this after every benchmark step.

**Q: Why integer paise instead of a Decimal money column?**
> `int` is exact. `NUMERIC(18,2)` in Postgres is also exact, but Python `Decimal` requires care
> (setting precision context). An `int` can't be accidentally divided or averaged. All rounding
> happens in named Python functions (`round_half_up`), which are unit-tested.

**Q: Why is the JWT role re-read from the DB on every request?**
> If a user is deactivated or their role is changed, a cached token would still be valid until
> expiry. Re-reading the DB ensures changes take effect immediately. The token only carries the
> `user_id`; the role comes from `auth.deps.get_current_user()`.

**Q: How does the variance flag handle the 3% boundary case?**
> `flag = abs(diff) × 10000 > tol_bp × planned`. With pouches: diff=600, planned=20000, tol=300.
> `abs(600) × 10000 = 6_000_000`, `300 × 20000 = 6_000_000`. They're equal, so NOT flagged.
> If we used the rounded bp (`var_bp=−300`) and compared `300 > 300`, the result is the same
> but the exact-value check is more robust (e.g. 3.004% rounded to 300 bp would slip through).

**Q: How does idempotency prevent duplicate orders from an offline phone?**
> The phone generates `client_uuid = crypto.randomUUID()` before the first send. That UUID is
> the `Idempotency-Key` header. The server stores key + request_hash + response in `idempotency_key`
> (committed in the same transaction as the order). A retry with the same key returns the stored
> response without creating a new order. `sales_order.client_uuid` has a UNIQUE constraint as a
> second guard against concurrent double-taps.

**Q: How does the invoice PDF get the ₹ symbol?**
> The `DejaVu` TTF font file is bundled inside `backend/app/billing/fonts/`. The font is loaded
> once by fpdf2. The `Dockerfile` copies `backend/` into the image, so the font ships with the
> container. No system fonts needed.

### Live Coding Challenges

**Challenge 1 (10 min): Write `apply_bp(100, 333)`**
> `round_half_up(Decimal(100) × Decimal(333) / Decimal(10000))`
> `= round_half_up(Decimal("3.33"))` → `3` (half-up: 3.33 rounds down to 3).

**Challenge 2 (10 min): Add a `GET /stock/balance` endpoint**
> Router: `@router.get("/stock/balance")`, depends on `require_roles(admin, auditor, owner)`.
> Service call: `inventory.balance(db, item_id)` → returns `(qty, value_paise)`.
> Schema: `class BalanceOut(BaseModel): qty: Decimal; value_paise: int`.

**Challenge 3 (15 min): Explain `post_movements` for a dispatch of 150 packets**
> 1. `lock_items(db, [FG_ITEM_ID])` — locks the row.
> 2. Line has `qty = -150`, `movement_type = DISPATCH`.
> 3. `balance(db, FG_ITEM_ID, as_of=movement_date)` → (238, total_value).
> 4. `issue_value(150, 238, total_value)` → WAC value.
> 5. `allocate(db, FG_ITEM_ID, 150)` → FIFO lot slices.
> 6. For each slice, check as-of balance AND current balance of that lot.
> 7. Insert `StockMovement` rows with negative qty and negative value.

**Challenge 4 (15 min): What does `reconcile()` check?**
> Per item: `SUM(qty) >= 0` and `SUM(value_paise) >= 0` and no value on zero stock.
> Per lot: `SUM(qty) >= 0`. Returns a list of problem strings; empty = healthy.
> This runs after every benchmark step as an invariant.

### Questions to Answer Live About Your Own Code

Before an interview, be able to answer these without looking:

1. Where exactly is `round_half_up` called, and why there and not elsewhere?
2. What is the `source_line_id` in a production run's ISSUE movement? What table does it point to?
3. Why does `complete_run()` compute `material = -inventory.source_value(db, RUN, run.id, ISSUE)`? Why the negative sign?
4. What does `db.expire(run, ["lines"])` do in `start_run()` and why is it needed?
5. What is the difference between `db.flush()` and `db.commit()`?
6. How does `FORMAT_INR` group digits differently from Western style (1,000,000 vs 10,00,000)?
7. Why does the salesman's localStorage key include the username (`ff.order.queue.{username}`)?
8. What does `SPAStaticFiles` do (in `core/spa.py`) that plain `StaticFiles` doesn't?
9. Why does `create_lot()` call `db.flush()` after adding the lot but before returning it?
10. How would you add a `500 g Murukku` SKU without changing any schema?

---

## 10. Quick Reference

### API Endpoints (implemented)

| Method | Path | Role | What it does |
|---|---|---|---|
| POST | `/auth/login` | any | Returns JWT |
| GET | `/auth/me` | any (logged in) | Current user |
| GET | `/items` | production, admin, auditor | List items |
| GET | `/boms` | production | List BOMs |
| GET | `/customers` | salesman, admin | List customers (filtered by salesman) |
| GET | `/price-list` | salesman, admin | Product prices |
| GET | `/suppliers` | production | List suppliers |
| POST | `/purchases` | production | Record a receipt |
| POST | `/production-runs` | production | Start a run (issues raw materials) |
| POST | `/production-runs/{id}/complete` | production | Record output + packaging |
| POST | `/production-runs/{id}/overheads` | production | Add labour/power costs |
| GET | `/production-runs/{id}/variance` | production, admin, auditor | Planned vs actual |
| GET | `/production-runs/{id}/cost` | production, admin, auditor | ₹ per packet |
| POST | `/orders` | salesman | Place an order (Idempotency-Key required) |
| GET | `/orders` | salesman (own), admin (all) | List orders |
| POST | `/orders/{id}/approve` | admin | Approve with stock check |
| GET | `/orders/{id}/tax-preview` | admin | GST estimate without creating anything |
| POST | `/orders/{id}/invoice` | admin | Raise a GST invoice |
| POST | `/invoices/{id}/dispatch` | admin | Dispatch (stock leaves) |
| POST | `/invoices/{id}/cancel` | admin | Credit note + reversal movements |
| GET | `/invoices/{id}/pdf` | admin, auditor | Download PDF |
| POST | `/payments` | admin | Record payment + allocation |
| GET | `/customers/{id}/outstanding` | admin, auditor | Derived outstanding balance |
| GET | `/stock/balance` | admin, auditor | Item balance from ledger |
| GET | `/stock/reconcile` | admin, auditor | Ledger health check |
| GET | `/reports/{name}` | admin, auditor, owner | sales-register, stock-summary, stock-ledger, production |

### Error Code Reference

| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHENTICATED` | 401 | Missing or invalid JWT |
| `FORBIDDEN` | 403 | Role not allowed for this action |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `INSUFFICIENT_STOCK` | 409 | Not enough stock to approve/dispatch |
| `RUN_ALREADY_COMPLETED` | 409 | Can't complete twice |
| `IDEMPOTENCY_CONFLICT` | 409 | Same key, different request body |
| `BOM_INACTIVE` | 422 | BOM is not active |
| `NOT_IN_BOM` | 422 | Item not in this run's BOM |
| `INVALID_QUANTITY` | 422 | Bad quantity format or scale |

### Key Files at a Glance

```
backend/app/core/money.py        ← round_half_up, to_paise, format_inr
backend/app/core/wac.py          ← receipt_value, issue_value, cost_per_unit_paise
backend/app/core/gst.py          ← supply_type, line_tax, invoice_no, financial_year
backend/app/inventory/service.py ← balance, post_movements, allocate, reconcile
backend/app/production/service.py← start_run, complete_run, add_overheads, run_cost
backend/app/sales/service.py     ← create_order (idempotency), approve_order
backend/app/billing/service.py   ← create_invoice, dispatch, cancel_invoice
backend/tests/benchmark/test_section5.py ← the full scenario (B1–B13)
frontend/src/format.js           ← inr, toPaise, decMul, localToday, showQty
frontend/src/offline/queue.js    ← makeQueue (enqueue, flush)
frontend/src/api/client.js       ← api, apiBlob
```

---

*Last updated: 2026-11-25. Based on codebase state at commit `afe5a07` (UI critique fixes).*
*If you add a new module or change a workflow, update section 4 (Exploration Roadmap) and add a walkthrough in section 6.*
