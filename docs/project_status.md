# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: P1b in progress (image ready; Render + Neon setup by the user)

P1b code is on `main`: root `Dockerfile` builds and was tested locally with `PORT=10000` and a plain
`postgresql://` URL (health 200, page 200). Remaining: the user creates the Neon DB and the Render web
service (Dockerfile Path `./Dockerfile`, env `DATABASE_URL`, `JWT_SECRET_KEY`), then we check the live URL.

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ✅ done |
| P1b | Early deploy (Render + Neon) | 🟡 image done, hosting pending |
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
Finish phase P1b. The production Dockerfile is already on main. I (the user) have created the Neon DB and
the Render web service (Dockerfile Path ./Dockerfile, env DATABASE_URL and JWT_SECRET_KEY set in the
dashboard). My live URL is: <paste it>. Check that <url>/api/v1/health returns {"status":"ok","db":"ok"}
and <url>/ shows the placeholder page; if not, read the Render deploy log I paste and fix it.
No keep-alive pings. Then /update-docs-and-commit, the teaching protocol for P1b, and an updated next
prompt for P2 (core maths: money, units, gst, wac, variance; pure and unit-tested).
```
