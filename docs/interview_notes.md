# Interview notes

One section per phase, written by the teaching protocol in [roadmap.md](roadmap.md).
Each section has the explanation, five likely questions with short answers, and one practice change.

## P1: Skeleton

### What it is
- A running but empty system: Postgres + FastAPI in Docker Compose, one health endpoint, migrations wired,
  tests on a separate database, lint, CI, and Claude Code guard-rails.
- The benchmark test is written **before** any feature. Every check is `xfail(strict=True)`, so the
  scoreboard shows exactly what is left, and a check can't silently start passing.

### The 3 files that matter
1. `backend/app/core/config.py`: every setting comes from the environment through one typed `Settings` object.
2. `backend/tests/conftest.py`: swaps in `TEST_DATABASE_URL` before the app is imported, then rebuilds the
   schema with the real Alembic migrations.
3. `backend/tests/benchmark/test_section5.py`: the PROBLEM §5 scenario as code. One fixture runs steps 1–9
   through the HTTP API, and each check B1–B13 is its own test.

### One trace: `GET /api/v1/health`
Browser → uvicorn → `app.main.create_app()` mounted `core.health.router` at `/api/v1` → `health()` gets a DB
session from `get_db()` → runs `SELECT 1` → `{"status": "ok", "db": "ok"}`, or 503 if the DB is down.

### Five likely questions
1. **Why write the benchmark test before the code?** It fixes the target numbers up front, so I can't bend
   the expected values to match whatever the code produces. Each phase just removes markers.
2. **What does `strict=True` add to xfail?** If a check passes while still marked xfail, the run *fails*.
   That forces me to remove the marker in the same commit as the code, so the scoreboard is always honest.
3. **How do tests avoid wiping your real data?** `conftest.py` refuses to run unless `TEST_DATABASE_URL` is set
   and different from `DATABASE_URL`, and points the app at it before anything connects.
4. **Why Alembic in tests instead of `Base.metadata.create_all()`?** Tests then exercise the same migrations
   production runs, including triggers that `create_all` would never create (the append-only ledger trigger in P3).
5. **What do the Claude hooks do?** Before any edit, a script blocks changes to `docs/PROBLEM.md` and real
   `.env` files (exit code 2 = block). After any edit to a `.py` file, ruff formats and lints it, and remaining
   errors are fed back to Claude.

Bonus: **Why sync SQLAlchemy, not async?** About 20 users. FastAPI runs sync endpoints in a thread pool, and sync
code is simpler to read, debug and explain.

### Practice change (do it alone)
Add a `version` field to the health response (`"version": "0.1.0"`, read from `app.version`) and update
`tests/integration/test_health.py` to expect it. Run `docker compose run --rm api pytest -q`.

## P1b: Early deploy

### What it is
- One container on Render Free serves both the API (`/api/v1/...`) and the built React page (`/`), backed by
  Neon Free Postgres. Every push to `main` redeploys automatically.
- Deploying on day 1 means hosting surprises show up now, not the night before the demo.

### The 3 files that matter
1. `Dockerfile` (repo root): stage 1 (Node) builds `frontend/`, stage 2 (slim Python) gets only the built files,
   installs runtime deps, runs as a non-root user, and starts with `alembic upgrade head` then uvicorn on `$PORT`.
2. `backend/app/core/spa.py`: serves the built files; unknown paths fall back to `index.html`, except `/api/...`.
3. `backend/app/core/config.py`: rewrites the host's `postgresql://` URL to the psycopg 3 driver.

### One trace: opening the live URL
Browser → Render proxy (HTTPS) → container on `$PORT` (10000) → FastAPI: `/` matches no API route, so the
static mount returns `index.html` → the page's JS calls `/api/v1/health` on the same origin (no CORS) →
`SELECT 1` on Neon → `{"status":"ok","db":"ok"}` shown on the page.

### Five likely questions
1. **Why a multi-stage build?** Node is only needed to build the page. The final image has Python and the
   built files, so it is smaller and has less to attack.
2. **Why read `$PORT` instead of hard-coding 8000?** Render chooses the port and passes it in. `${PORT:-8000}`
   uses Render's value there and 8000 locally.
3. **Why run migrations at container start?** The free plan has no separate release step, and with one
   instance there is no race. `alembic upgrade head` is a no-op when the schema is already current.
4. **What broke on the first deploy?** Render's Root Directory was `docker/`, so it looked for
   `docker/Dockerfile` and found nothing. The build log said `open Dockerfile: no such file or directory`.
   Fix: clear Root Directory so the build context is the repo root.
5. **Why no keep-alive pings to avoid the cold start?** Neon's free tier counts compute hours. Pings would keep
   the DB awake and burn them. A ~1 min first load is fine for a demo, and the README will say so.

### Practice change (do it alone)
Show the API version on the placeholder page: add `"version"` to the health response (the P1 practice change)
and render it in `frontend/src/App.jsx`. Build with `docker build -t factoryflow .` and run it locally
with `-e PORT=10000`.

## P2: Core maths

### What it is
- Five pure modules in `backend/app/core/` with no database and no HTTP: `money`, `units`, `gst`, `wac`,
  `variance`. Every number in the benchmark comes out of these, so they are tested on their own first.
- Pure functions are fast to test (64 tests in under a second) and easy to explain line by line.

### The 3 files that matter
1. `core/money.py`: `round_half_up` (the only rounding function), `apply_bp`, `format_inr`.
2. `core/wac.py`: `receipt_value`, `issue_value` (with the anti-drift rule), `cost_per_unit_paise`.
3. `core/gst.py`: `supply_type` by state, `line_tax` per line, `financial_year`, `invoice_no`.

### One trace: B13 cost per packet (`tests/unit/test_wac.py::test_b13_cost_per_packet`)
Flour WAC: (100 kg × 42 + 60 kg × 45) / 160 kg = 43.125 → `issue_value(40000 g, 160000 g, 690000)` = 172500
→ add oil 147000, spice 24000, pouches 48500 (194 incl. 6 damaged), cartons 13500 = 405500 materials
→ + 180000 overheads = 585500 → `cost_per_unit_paise(585500, 188)` = 3114.36 → **3114 paise = ₹31.14**.

### Five likely questions
1. **Why paise and not float?** Floats can't store 0.1 exactly, so totals drift. Integer paise are exact; we
   round only at four named points (receipt value, issue value, each tax component per line, cost per unit).
2. **Why half-up and not Python's `round()`?** `round()` is banker's rounding (2.5 → 2). Invoices and auditors
   expect 2.5 → 3. `Decimal.to_integral_value(ROUND_HALF_UP)` does exactly that.
3. **Why tax per line and not on the total?** The printed lines must add up to the printed total. Example in
   the tests: two lines of 1010 paise at 5% IGST are 51 + 51 = 102, while 5% of 2020 would be 101.
4. **What is the anti-drift rule?** An issue that empties the stock takes all the remaining value. Without it,
   3 units worth 100 paise issued one by one leave a stray paisa on zero stock forever.
5. **Why is exactly −3.00% on pouches not flagged?** Our assumption A2 says "beyond 3%" means strictly greater.
   And the flag uses the exact values, so +3.004% (which rounds to 300 bp) is still flagged.

Bonus: **Why compute purchase value before converting to grams?** ₹45/kg is 4.5 paise per gram, which isn't a
whole paisa. 60 kg × 4500 paise is exact.

### Practice change (do it alone)
Add `credit_note_no(fy, seq)` to `core/gst.py` returning `FF/CN/2026-27/0001` (the format in the gst-rules
skill), with a test for seq 1 and seq 0 (error). Run `docker compose run --rm api pytest tests/unit -q`.

## P3: Auth, masters, ledger, audit, seed

### What it is
- Who can log in and what each role may call; the master data (items, BOMs, customers, suppliers, prices);
  the stock ledger every later phase posts to; an audit trail; and a seed with the benchmark's data.
- Stock is never stored as a number to overwrite. It is `SUM()` of an append-only list of movements.

### The 3 files that matter
1. `backend/app/inventory/service.py`: `post_movements()`, the only writer of stock. Lock the items, check,
   pick lots FIFO, value outflows at WAC, insert. It never commits; the calling service does.
2. `backend/alembic/versions/20261123_40b955c1df42_auth_masters_ledger_audit.py`: the tables plus the
   append-only trigger on `stock_movement` and `audit_log`.
3. `backend/app/auth/deps.py`: `get_current_user` and `require_roles()`, deny by default.

### One trace: `GET /api/v1/stock/balance/1` as `production`
Bearer token → `require_roles(admin, production, auditor, owner)` → `get_current_user` decodes the JWT (only
the user id) and re-reads role and active flag from the DB → allowed → `masters.get_item` (404 if missing) →
`inventory.balance()` = `SELECT SUM(qty), SUM(value_paise) FROM stock_movement WHERE item_id = 1` →
`{"qty": "100000.000", "uom": "g", "value_paise": 420000}` (100 kg of flour at ₹42).

### Five likely questions
1. **What stops someone editing stock?** There is no balance column to edit: stock = `SUM(ledger)`. The ledger
   is append-only (a DB trigger rejects UPDATE, DELETE and TRUNCATE), only `post_movements()` inserts, and the
   DB also rejects bad rows: no source document, a lot of another item, or a sign that doesn't match the type.
   Mistakes are corrected with new movements.
2. **Two people issue the last 10 kg at the same moment. What happens?** `post_movements()` locks the item rows
   (`SELECT … FOR UPDATE`, always in id order so two transactions can't deadlock) before reading the balance.
   The second one waits, then sees the lower balance and gets `INSUFFICIENT_STOCK`.
3. **How do you prove "deny by default"?** A test walks every route and fails if one lacks `require_roles()`,
   except `/health` and `/auth/login`. A role matrix test checks real answers, e.g. production gets 403 on
   customers (it never sees sales data) and the auditor gets 403 on any POST.
4. **Why re-read the user on every request instead of trusting the role in the token?** Tokens live 10 hours.
   Re-reading means a disabled account or a changed role takes effect at once; the token only proves identity.
5. **Is even the opening stock traceable?** Yes. It is a real document (`stock_adjustment`, kind OPENING) with
   lines, and each movement points at it. After every benchmark step and every integration test, an invariant
   check runs reconcile, compares API balances with `SUM(ledger)` and counts orphans.

Bonus: **Why doesn't the weak-JWT-key check use a pydantic validator?** A pydantic error prints the input
values, which would put the database URL and keys into Render's logs. A plain `RuntimeError` prints only the
message.

### Practice change (do it alone)
Add a stock-take endpoint: `POST /api/v1/stock/adjustments` (roles admin, production) taking lines
`{item_id, qty (signed), uom}`. Create a `stock_adjustment` (kind ADJUST) with lines, post `ADJUST` movements
through `post_movements()`, write an audit row, commit. Test: flour counted at 98 kg → post −2 kg → balance
98 kg and `reconcile()` is clean. Hint: a negative adjustment is valued at WAC by `post_movements()`; a positive
one needs a value (use the current average cost).

## P4: Purchases and production runs

### What it is
- **Purchases** bring stock in: one lot per line, valued at what was paid before tax.
- **Production runs** turn materials into finished goods: issue raw materials, issue packaging, post the
  good output at material cost, compare actual with the BOM (variance), add overheads, get cost per packet.

### The 3 files that matter
1. `backend/app/production/service.py`: `start_run`, `complete_run`, `add_overheads`, `run_variance`, `run_cost`.
2. `backend/app/purchasing/service.py`: `create_purchase`.
3. `backend/tests/integration/test_production.py`: the benchmark flow through the API, including B13.

### One trace: `POST /api/v1/production-runs/1/complete` (step 3 of the benchmark)
`require_roles(production)` → lock the run row → still DRAFT? → issue 194 pouches and 9 cartons through
`post_movements()` (item locks, FIFO lots, WAC: 48500 + 13500 paise) → read actual consumption back from the
ledger → record 6 damaged pouches (must be ≤ issued) → create FG lot `RUN-0001` (expiry run date + 90 days) →
material cost = −SUM(the run's ISSUE values) = 405500 → post OUTPUT +188 packets at 405500 → status COMPLETED →
audit row with before/after → one commit.

### Five likely questions
1. **Why WAC and not FIFO costing?** Flour from two purchases sits in one bin. WAC gives one honest unit cost
   (₹43.125/kg) that is easy to audit. FIFO costing would need lot-level costs for every issue. Lots still exist
   and are picked FIFO, but only for traceability and expiry.
2. **How is variance flagged?** Planned = BOM × batches. Variance = (actual − planned) / planned, in basis points.
   Flag when the exact |variance| is beyond the item's tolerance (3% by default, strictly). Oil +5% and yield
   −6% are flagged; pouches at exactly −3.00% are not (A2).
3. **Why aren't the 6 damaged pouches a separate movement?** They left the store inside the 194 issued: one
   physical movement. Recording damage as information avoids counting it twice (pouches closing = 500 − 194 = 306).
4. **Why not store actual consumption on the run?** It already lives in the ledger as ISSUE movements. Reading it
   from there means the production report and the stock ledger can never disagree.
5. **What if a start fails halfway, e.g. oil issued but flour short?** It is one transaction: the run, its lines,
   the oil issue and the audit row all roll back. The API answers 409 `INSUFFICIENT_STOCK` naming FLOUR and the
   shortage, and a test proves no run or movement row was left behind.

Bonus: **Why is ₹31.14 proven in a P4 test while the benchmark's B13 still waits?** In PROBLEM §5 the overheads
are step 8, after the orders and the payment, so the scenario can only reach it once P5 and P6 exist.

### Practice change (do it alone)
Add **Murukku 500 g** sharing the same ingredient lines: create a `POUCH-500G` packaging item and the
`MURUKKU-500G` product (`POST /items`), then its BOM (`POST /boms`) with the same flour, oil and spice lines but
its own pouch and, say, 80 packets per batch. Buy some pouches (`POST /purchases`), run one batch, and check
`/variance` and `/cost`.

### P4 hardening (what the hostile audit found)
The `ledger-auditor` subagent wrote 56 tests and found 9 real defects before P4 merged. Worth being able
to recount one or two:
- **Backdated issue (critical):** a run dated 2 Nov could consume flour received on 20 Nov, showing −4 kg on
  2 Nov, and `reconcile()` (which looks at *current* totals) stayed green. Fix: `post_movements` reads the
  balance **as of the movement date**, so stock can't be drawn before it arrived.
- **Posted documents were editable/deletable.** Only the ledger had the append-only trigger, so `UPDATE
  production_run SET good_qty` quietly changed cost per packet. Fix: DB triggers freeze the documents too (a
  run is immutable once COMPLETED), so the report can't diverge from the ledger it's supposed to summarise.
- **Lock-order deadlock:** two concurrent runs each inserted rows (a weak FOR KEY SHARE lock) before asking
  for FOR UPDATE, so Postgres killed one with a 500. Fix: lock the items first; the loser now waits and gets
  a clean 409.
The lesson for the interview: an invariant you only check against *current* state (reconcile) misses history;
the strongest guarantees are the ones the database enforces (triggers, as-of queries), not the service layer.

## P5: Orders, invoice, dispatch and credit notes

### What it is
- The **sales** side of the order-to-cash loop: a salesman places an order (priced by the server), the admin
  approves it against a stock-cover check, raises a GST invoice, and dispatches the goods.
- A posted invoice is never deleted; it is **cancelled with a credit note** whose reversing movements put the
  stock back exactly. Orders are **idempotent**, so an offline phone that sends the same order twice lands one.

### The 3 files that matter
1. `backend/app/sales/service.py`: `create_order` (idempotency + server pricing), `approve_order` (stock check),
   `tax_preview`.
2. `backend/app/billing/service.py`: `create_invoice` (FY numbering), `dispatch_invoice`, `cancel_invoice`.
3. `backend/app/inventory/service.py`: `post_movements` (DISPATCH outflow) and the new `post_reversals`
   (credit-note REVERSAL, the mirror).

### One trace: `POST /api/v1/orders/1/invoice` (step 5 of the benchmark)
`require_roles(admin)` → lock the order row → still APPROVED? → place of supply = customer state (33 = ours →
INTRA) → FY from the invoice date (`2026-11-03` → `2026-27`) → `_next_seq`: `INSERT … ON CONFLICT DO NOTHING`
then `SELECT … FOR UPDATE` the FY row and bump it → number `FF/2026-27/0001` → per line, taxable 150×5000 =
750000, CGST 2.5% = 18750, SGST 2.5% = 18750 (each rounded on its own) → totals 787500 → order → INVOICED →
audit row → one commit. Dispatch is a separate call; that is where the 150 packets actually leave stock.

### Five likely questions
1. **Same-state vs other-state tax?** Place of supply is the customer's state. Same as the company (33, TN) →
   intra-state → CGST + SGST, half the rate each. Different (29, KA) → inter-state → IGST, the full rate. Never
   both. Tax is computed and rounded **per line**, then summed, so the printed lines always add to the total.
2. **Double-tap offline — how do you avoid two orders?** The phone sends a `crypto.randomUUID()` as the
   `Idempotency-Key`; it becomes the order's UNIQUE `client_uuid` and a row in `idempotency_key` (with the
   request hash and the stored response). Same key + same body → replay the first order; different body → 409;
   a concurrent race is caught at the flush by the UNIQUE violation and replays the winner. Replay is scoped to
   the user who owns the key, so another salesman can't fish out the order with a stolen key.
3. **How is invoice numbering gapless, even under concurrency or a failure?** A `FOR UPDATE` row per FY in
   `invoice_sequence`: concurrent invoices serialise on it, and because the bump lives in the invoice's own
   transaction, a rolled-back invoice un-bumps the number — no gaps, no duplicates.
4. **What does "approve" reserve, and how is availability computed?** No stock moves at approval. Availability =
   finished goods on hand − what approved-but-undispatched orders already claimed; over-approval returns 409
   `INSUFFICIENT_STOCK` with requested/available/shortage. The item row is locked, so the check can't race a
   dispatch. Stock leaves only on dispatch (a `DISPATCH` movement valued at WAC).
5. **How does cancelling an invoice keep the books exact?** `cancel` writes a `credit_note` and
   `post_reversals()` posts one `REVERSAL` per dispatch movement — same lot, **opposite** qty and value, with
   `reverses_id` pointing at the original (UNIQUE, so a movement is reversed at most once). Mirroring the exact
   numbers (not recomputing) means stock and the item's WAC return to precisely where they were; the invoice
   number stays used (A12).

Bonus: **Why is dispatch, not the invoice, the moment stock leaves?** An invoice is a financial document; the
goods can be billed and shipped at different times. Keeping the `DISPATCH` movement on the dispatch means the
ledger reflects physical reality, and a cancelled-before-dispatch invoice reverses no stock.

### Practice change (do it alone)
Make the invoice prefix include a branch code. `gst.invoice_no(fy, seq, prefix)` already takes the prefix from
`company_settings.invoice_prefix`; add a `branch_code` (e.g. `TRY`) and have billing build numbers like
`FF-TRY/2026-27/0001`. Add a test that two branches keep **independent** gapless sequences (hint: the sequence
key would need the branch as well as the FY).

### P5 hardening (what the hostile audit found)
The `ledger-auditor` confirmed three defects before P5 merged (17-test guard suite in `tests/audit/`):
- **Backdated out-of-order dispatch (critical):** dispatch dates are admin-supplied, and the outflow check only
  looked *as of* that date. Two dispatches out of order could drive a lot to −100 on a past date while the
  current total stayed positive, so `reconcile()` only caught it after the fact. Fix: an outflow now also checks
  the **current** per-lot balance; a lot has one inflow, so now is its lowest point.
- **Idempotency double-tap 500 (minor):** the UNIQUE violation fires at the flush, not the commit, so the
  losing caller escaped the replay handler and got a 500. Fix: wrap the whole create, flush included.
- **Replay ignored who was asking (minor):** another salesman presenting a stolen key + body was handed the
  order. Fix: `_replay` checks the key's owner.
The lesson: as-of and current are *different* invariants — a safe historical ledger needs the running balance
to stay non-negative at **every** date, not just the latest.

## P6: Payments and outstanding (the benchmark gate)

### What it is
- Money received from a customer, **allocated** to their invoices. "Outstanding" (what they still owe) is
  computed from invoices and payments on demand, not stored.
- Landing P6 turns the whole PROBLEM §5 benchmark green, so the scope gate in CLAUDE.md opens.

### The 3 files that matter
1. `backend/app/payments/service.py`: `record_payment` (allocation + the over-allocation lock) and
   `customer_outstanding` (the derived balance).
2. `backend/app/payments/models.py`: `payment` and `payment_allocation` (append-only).
3. `backend/tests/integration/test_payments.py` + `tests/audit/test_p6_payments_audit.py`.

### One trace: `POST /api/v1/payments` (step 7 of the benchmark)
`require_roles(admin)` → load the customer → allocations must sum to the amount (else 422) → no duplicate
invoice → `SELECT … FOR UPDATE` the allocated invoices → for each: it belongs to the customer, is not
cancelled, and already-allocated + this ≤ its total (else 409 `OVER_ALLOCATION`) → insert the payment and its
allocations → audit → one commit. Then `GET /customers/1/outstanding` returns 7875 − 4000 = **3875** (B11).

### Five likely questions
1. **How is outstanding derived, and why not store it?** `invoice.total − SUM(allocations)` over non-cancelled
   invoices. Storing a running balance would be a second source of truth that can drift from the payments; a
   `SUM()` on read can't. Same principle as stock = `SUM(ledger)`.
2. **How do you stop two payments from over-paying one invoice at once?** The invoice row is locked
   `FOR UPDATE` before the check, so a concurrent payment to it waits, then re-reads the committed allocations
   and sees there's no room left — the loser gets 409, not a double payment. (Proven by a threaded audit test.)
3. **Why do payments post nothing to the stock ledger?** The ledger is about *stock*. Money owed is a
   different fact, derived from invoices and payments. Keeping them separate means a payment can never
   accidentally move inventory, and the stock invariants are untouched by cash.
4. **What happens to a payment if its invoice is later cancelled?** The cancelled invoice drops out of
   outstanding, and paying a cancelled invoice is refused up front. (Refunding an already-paid, then-cancelled
   invoice is future work, not in the prototype.)
5. **What makes this the "benchmark gate"?** B11 needs the payment (step 7) and B13's cost needs the overheads
   (step 8, which only runs once step 7 passes). With payments in, every B-check passes, so CLAUDE.md's rule
   "nothing beyond the must-have tier until the benchmark passes" is satisfied.

Bonus: **One thing the audit flagged.** `POST /payments` has no `Idempotency-Key`, so a retry posts a second
receipt. It can't drift money (the over-allocation cap holds), but it's worth adding in P8 alongside the
offline queue — the same `Idempotency-Key` machinery orders already use.

### Practice change (do it alone)
Add a **61–90 day ageing bucket** to `GET /customers/{id}/outstanding`: group each invoice's outstanding by
how old it is (0–30, 31–60, 61–90, 90+) relative to a `?as_of=` date, and return the bucket totals. Add a test
with invoices dated across the boundaries.

### P6 hardening (what the hostile audit found)
The `ledger-auditor` wrote 21 tests and confirmed **no** break — every money-integrity control held. The one
worth recounting is the concurrency guard: two payments racing to pay the same invoice in full are serialised
by the `FOR UPDATE` lock, so exactly one commits and the committed sum of allocations equals the invoice total,
never twice it. The lesson: the moment a check reads-then-writes a shared total, a row lock (not just the
application check) is what makes it safe under concurrency.
