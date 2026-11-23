# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P1b done. Next: **P2 core maths**

**Live:** https://factoryflow-icdx.onrender.com (Render Free, Singapore, auto-deploys from `main`; Neon Free DB).
Verified 2026-11-23: `/api/v1/health` → `{"status":"ok","db":"ok"}`, `/` serves the placeholder page.
First deploy failed because Render's **Root Directory** was `docker/` (it must be empty); fixed in the dashboard.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | ✅ done |
| P2–P6 | Core maths → ledger → production → sales/invoice → payments (benchmark gate) | ⚪ |
| P7–P9 | PDF + reports → frontend + offline queue → README/design note/deploy | ⚪ |
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

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- Render: Health Check Path is still empty; set it to `/api/v1/health` in the dashboard (optional, recommended).
- Every push to `main` redeploys Render (about 1 min), including docs-only pushes.
- `gh` CLI not installed; pushes use plain git.
- Two Dockerfiles on purpose: root `Dockerfile` = production (Render); `backend/Dockerfile` = dev (compose,
  includes pytest/ruff, live reload).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 9 passed, 19 xfailed (2026-11-23). Every check currently stops at step 0 (`app.seed` not built).

| Check | Status |
|---|---|
| B1–B13, B9b, B10b, B12b | ⏳ xfail |
| ledger reconciles · no orphan movements · salesman 403 on approve | ⏳ xfail |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
Start phase P2 on branch feat/p2-core-maths, exactly as defined in docs/roadmap.md:
pure modules in backend/app/core/ — money (integer paise, half-up rounding), units (to_base with Decimal,
kg/g, l/ml, pcs, pkt; cross-dimension = error), gst (CGST+SGST vs IGST by state, per-line half-up),
wac (moving weighted average, anti-drift on emptying issue), variance (bp, flag when |var| > tol strictly).
No DB, no HTTP. Unit tests in backend/tests/unit/ covering the spec §4 numbers (B8, B9, B9b, B10, B12b
taxes, B13 arithmetic). Benchmark checks stay xfail (they need the API). Finish with tests and lint green,
/update-docs-and-commit, merge to main, the teaching protocol, and an updated next prompt for P3.
```
