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
