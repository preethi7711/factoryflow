# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P1 done. Next: **P1b early deploy**

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | ⚪ next |
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
- Render signup: confirm no card is asked (P1b). If one is, fall back to local compose + video.
- `gh` CLI not installed; pushes use plain git.
- Docker Desktop crashed during P1 and then gave "unable to get image … unexpected end of JSON input".
  The suite ran green in Docker before that. Not re-verified after the crash: the live
  `curl localhost:$API_PORT/api/v1/health` and the first GitHub Actions run (CI runs on push).
- Local `backend/.venv` exists only so the ruff hook works on the host (git-ignored).

## Benchmark scoreboard

`pytest -q`: 3 passed, 19 xfailed (2026-11-23). Every check currently stops at step 0 (`app.seed` not built).

| Check | Status |
|---|---|
| B1–B13, B9b, B10b, B12b | ⏳ xfail |
| ledger reconciles · no orphan movements · salesman 403 on approve | ⏳ xfail |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
First confirm Docker Desktop is healthy: `docker compose up -d` then
`curl localhost:8000/api/v1/health` (use API_PORT=8001 if 8000 is busy) and
`docker compose run --rm api pytest -q` (expect 3 passed, 19 xfailed).
Then start phase P1b on branch feat/p1b-deploy, exactly as defined in docs/roadmap.md:
multi-stage Dockerfile (build a placeholder React/Vite page, FastAPI serves dist/ at / and the API at
/api/v1), Render Free web service auto-deploying from main, Neon Free Postgres. I (the user) create the
Render and Neon accounts myself and confirm no credit card is asked; if one is, stop and fall back to local
compose + demo video. DATABASE_URL and JWT_SECRET_KEY go in the Render dashboard, never in the repo.
No keep-alive pings. Done when the live URL shows /api/v1/health OK and the placeholder page.
Finish with /update-docs-and-commit, merge to main, the teaching protocol, and an updated next prompt for P2.
```
