# Project status (session handoff file)

_Last updated: 2026-11-23_

## Current phase: 0 done (plan approved). Next: **P1 skeleton**

| Phase | Goal | Status |
|---|---|---|
| 0 | Repo, docs, conventions, plan, skills, auditor agent | ✅ done |
| P1 | Skeleton + CI + hooks + benchmark test (all xfail) | ⚪ next |
| P1b | Early deploy (Render + Neon) | ⚪ |
| P2–P6 | Core maths → ledger → production → sales/invoice → payments (benchmark gate) | ⚪ |
| P7–P9 | PDF + reports → frontend + offline queue → README/design note/deploy | ⚪ |
| P10–P11 | Should-haves → stretch | ⚪ |

Full roadmap: [roadmap.md](roadmap.md).

## Decisions made
- Stack: FastAPI + SQLAlchemy 2 + Alembic + Postgres 16; React + Vite + Tailwind in **plain JS**; one deployable.
- Lot/expiry on every movement from day one. Allocation FIFO; FEFO is stretch.
- WAC per item, overheads per run ÷ good output, so cost/packet = ₹31.14 (spec B13).
- Hosting: Render Free web + Neon Free Postgres. No keep-alive pings.
- Minimal offline order queue in P8. Six seeded logins (spec §2).
- No MCP servers. `pyright-lsp` plugin: **only if it works with no extra setup, and only after the user approves.** It needs `npm i -g pyright`, so the default is to skip it.

## Open issues
- Hours/day unconfirmed (assumed ~6, H1).
- Render signup: confirm no card is asked (P1b). If one is, fall back to local compose + video.
- `gh` CLI not installed; pushes use plain git.

## Benchmark scoreboard

| Check | Status |
|---|---|
| B1–B13 (+ b-checks, reconcile, orphans, RBAC) | ⚪ test not written yet |

## Next prompt (paste this to start the next session)

```
Read CLAUDE.md and docs/project_status.md, then continue.
Start phase P1 on branch feat/p1-skeleton, exactly as defined in docs/roadmap.md:
docker compose (db, api), FastAPI app with /api/v1/health, config from .env, Alembic, pytest with a
separate test DB, ruff, GitHub Actions CI, project hooks (.claude/settings.json: block edits to
docs/PROBLEM.md, .env, .env.local and other .env.* except .env.example; ruff on edited .py files), and
backend/tests/benchmark/test_section5.py with every check from docs/project_spec.md §4 marked
xfail(strict=True). Also create docs/interview_notes.md. Finish with tests green,
/update-docs-and-commit, merge to main, the teaching protocol, and an updated next prompt for P1b.
```
