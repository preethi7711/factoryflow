# Changelog

All notable changes, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Each milestone adds a section. Commit hashes are in `git log`.

## [Unreleased]

### Added
- P2 core maths in `backend/app/core/` (pure, no DB/HTTP): `money` (paise, half-up, Indian ₹ format),
  `units` (Decimal `to_base`/`from_base`, item packs, cross-dimension errors, floats refused), `gst`
  (INTRA/INTER, per-line tax, FY, invoice numbers, soft GSTIN checks), `wac` (receipt/issue value with
  anti-drift, cost per unit), `variance` (bp + strict exact-value flag). 64 unit tests, incl. B8–B10, B12b,
  B13 and A5 arithmetic.

### Changed
- Architecture: variance flag uses exact values; rounding points listed in one place.

## P1b deploy

### Added
- P1b: root multi-stage `Dockerfile` (Node builds `frontend/`, slim Python serves API + built files as a
  non-root user, listens on `$PORT`, runs `alembic upgrade head` on start) and root `.dockerignore`.
- Placeholder React + Vite frontend (`frontend/`) showing live API/DB health.
- FastAPI serves the built app (`STATIC_DIR`) with an index.html fallback for client routes; `/api` stays JSON 404.
- `DATABASE_URL` from hosts (`postgres://`, `postgresql://`) is rewritten to the psycopg 3 driver.
- CI job that builds the production image.
- Deployed: https://factoryflow-icdx.onrender.com (Render Free + Neon Free), health and page verified live.

### Fixed
- First Render deploy failed (`open Dockerfile: no such file or directory`): the service's Root Directory
  was `docker/`. Cleared it in the Render dashboard; no code change.

## P1 skeleton

### Added
- P1 skeleton: `docker-compose.yml` (db + api, test DB created on first start, `API_PORT` override),
  FastAPI app with `GET /api/v1/health` (checks the DB), typed settings from env, Alembic wiring (no tables yet).
- pytest on a separate `factoryflow_test` DB rebuilt by migrations; ruff config; GitHub Actions CI
  (lint + tests on Postgres 16).
- `backend/tests/benchmark/test_section5.py`: PROBLEM §5 steps 1–9 through the HTTP API, every spec §4
  check as its own `xfail(strict=True)` test.
- Claude Code project hooks (`.claude/settings.json`): block edits to `docs/PROBLEM.md` and `.env*`
  (except `.env.example`); ruff format + fix on edited `.py` files.
- `docs/interview_notes.md` (teaching protocol output, starting with P1).

### Changed
- `.env.example`: added `TEST_DATABASE_URL`.

## Phase 0

### Added
- Phase 0 setup: problem statement (verbatim), `CLAUDE.md`, `.env.example`, `.gitignore`, `.gitattributes`.
- Docs: `project_spec.md` (requirements, tiers, benchmark numbers, assumptions), `architecture.md` (provisional),
  `project_status.md`, this changelog.
- Claude Code slash command `/update-docs-and-commit`.
- Approved plan: `architecture.md` (stack, hosting, ER diagram, invariant mechanisms), `roadmap.md`
  (P1–P11, cut lines, wow list, teaching protocol), spec test logins and assumptions A13–A15, H1.
- Project skills `stock-ledger`, `gst-rules`, `benchmark-check`, and subagent `ledger-auditor`.

### Changed
- A5: opening finished goods valued at standard material cost ₹19.85/pkt.
- Offline order queue moved from stretch into P8 (§4.1 "strongly preferred").
- CLAUDE.md: plain JS frontend, single deployable, hosting, handoff and xfail rules.
