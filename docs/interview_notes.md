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
