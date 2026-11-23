# Changelog

All notable changes, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Each milestone adds a section. Commit hashes are in `git log`.

## [Unreleased]

### Added
- P4 `purchasing`: `POST /purchases`, `GET /purchases/{id}`. One lot per line, stock in base units at the
  quoted-unit value, input GST (CGST+SGST or IGST by supplier state) recorded but not costed (A15).
- P4 `production`: `POST /production-runs` (start + raw issues), `POST /{id}/complete` (packaging issues,
  damaged info, FG lot with expiry, OUTPUT at material cost), `POST /{id}/overheads` (COST_ADJUST),
  `GET /{id}`, `/variance` (B8, B9, B9b, A4) and `/cost` (B13: ₹31.14). Actual consumption is read from the
  ledger. Every step is audit-logged; a run can't be completed twice.
- Benchmark: B1–B6, B8, B9, B9b pass. B13 is proven by `tests/integration/test_production.py`.
- `core/clock.py` (IST business time); stock errors name the short item; assumption A18 (overhead date).
- `ledger-auditor` P4 hostile audit suite in `tests/audit/` (56 tests: 47 guards + 9 findings).

### Fixed
- P4 ledger-audit findings (all 9, tests now green): backdated issues can no longer overdraw stock
  on the movement date (balances read as of `movement_date`); `post_movements()` refuses an unknown
  source document and the orphan invariant actually checks existence; posted documents are append-only
  at the DB (a completed run or a purchase can't be edited or deleted, so `/cost` and `/variance` can't
  diverge from the ledger); concurrent posts lock items before inserting, so one gets 409 instead of a
  deadlock 500; one rounding point per issue line; whole-number pcs/pkt; `COST_ADJUST` must add value;
  BOMs are admin-only (segregation of duties).

## P3 auth, masters, ledger, audit, seed

### Added
- P3 `auth`: `app_user` with 5 roles, bcrypt passwords, JWT login (`POST /auth/login`, `GET /auth/me`),
  `require_roles()` deny-by-default, a test that fails if any route forgets it, and a role matrix test.
- P3 `masters`: items (+ pack units), BOMs stored in base units (one active per product), customers and
  suppliers (soft GSTIN warnings), price list (`item.sale_price_paise`), company settings. GET + POST endpoints.
- P3 `inventory`: `stock_movement` ledger (append-only trigger, composite lot/item FK, sign CHECK,
  `movement_date`), lots, `stock_adjustment` documents, `post_movements()` as the only writer (item locks,
  FIFO lot allocation, WAC values, anti-drift), `balance()`, `reconcile()`, `GET /stock/balance/{id}`,
  `GET /stock/reconcile`.
- P3 `audit`: append-only `audit_log`, written in the same transaction as the change.
- Seed (`python -m app.seed`): PROBLEM §5 masters, opening stock as an OPENING document, six demo logins.
- Error format `{"error": {"code", "message", "details"}}` for every failure, including 404/422.
- Ledger invariants (reconcile, API = SUM(ledger), no orphans) checked after every benchmark step and after
  every integration test. Benchmark: reconcile and orphan checks now pass.
- Production refuses to start with a weak `JWT_SECRET_KEY` (32+ characters), without logging any value.
- Assumptions A16 (shelf life 90 days) and A17 (opening stock dated 31 Oct 2026).

## P2 core maths

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
