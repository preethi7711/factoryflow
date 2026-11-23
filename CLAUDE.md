# FactoryFlow: Claude Code guide

Order-to-Audit system for a small South Indian snack manufacturer (NIT Trichy CDI internship task).
Read this first. It is short on purpose: details live in `docs/` and are imported, not copied.

## Project docs (imported, never duplicated here)

@docs/project_spec.md
@docs/architecture.md
@docs/project_status.md

Linked, not imported (large or append-only; open only when needed):
- [docs/PROBLEM.md](docs/PROBLEM.md): original problem statement, verbatim. **Never edit.**
- [docs/changelog.md](docs/changelog.md): what changed, per milestone.

**Rule:** when a fact already lives in a doc, reference it with `@docs/...` or a link. Do not paste it into
CLAUDE.md, a skill, or a prompt. One source of truth per fact.

## 1. Project overview

- Two loops meet at finished-goods stock:
  - **Sales:** order → approve → GST invoice → dispatch → receivables.
  - **Production:** purchase → issue per BOM → run → output, variance, cost per packet.
- Both loops feed the monthly auditor reports.
- Roles: salesman (mobile), admin, production supervisor, auditor (read-only), owner.
- Success = the **section 5 benchmark** passes as an automated test. Everything else comes after that.

## 2. Architecture overview (provisional until the plan is approved)

- **Modular monolith**: one backend process, one database, modules with clear boundaries.
- Backend: Python FastAPI + SQLAlchemy 2 + Alembic; PostgreSQL. Frontend: React + Vite + Tailwind PWA.
- Modules: `auth`, `masters`, `inventory` (ledger), `production`, `sales`, `billing`, `payments`,
  `costing`, `reports`, `audit`.
- **The ledger is the heart.** `inventory` owns `stock_movement`. Other modules post movements
  through `inventory.service`; they never write the table directly.
- Full design: @docs/architecture.md

## 3. Design style

**Code**
- Python: type hints everywhere, `ruff` for lint and format, small pure functions for the maths.
- TypeScript: `strict` mode, ESLint + Prettier, function components and hooks.
- Business maths (units, tax, costing, variance) lives in pure modules with no DB or HTTP, so it can be unit-tested.

**Naming**
- Tables: singular snake_case (`stock_movement`, `production_run`).
- Money columns end in `_paise` (integer). Quantity columns end in `_qty` (Numeric) next to a `uom` column.
- Python: snake_case. TS: camelCase vars, PascalCase components. API JSON: snake_case.

**Folder layout (target)**
```
backend/app/<module>/{models.py, schemas.py, service.py, router.py}
backend/app/core/        # config, db, security, money, units
backend/tests/           # unit/, integration/, benchmark/
backend/alembic/         # migrations
frontend/src/{pages,components,api,offline}/
docs/                    # spec, architecture, status, changelog, PROBLEM
```

**API conventions**
- REST under `/api/v1`. Nouns for resources, plus explicit actions for state changes:
  `POST /orders/{id}/approve`, `POST /invoices/{id}/cancel`.
- Money goes over the wire as integer paise, quantities as decimal **strings** (never JSON floats).
- Creating requests accept an `Idempotency-Key` header; a replayed key returns the original result.
- Errors use `{"error": {"code": "INSUFFICIENT_STOCK", "message": "...", "details": {...}}}`.
- Each endpoint declares the roles allowed to call it. Deny by default.

## 4. Constraints and invariants (non-negotiable)

1. **Free and open-source only.** No paid services, no credit card. Check official free-tier docs before recommending a host.
2. **Money = integer paise.** Never `float`. Round only at defined points (per line tax, half-up), and document each one.
3. **Quantities = exact decimals** (`Decimal` / `NUMERIC`), stored in the item's **base unit**.
4. **Stock is derived, never stored-and-overwritten.** Balance = SUM(ledger). Any cached balance must reconcile with the ledger, and a test proves it.
5. **The ledger is append-only.** No UPDATE or DELETE on `stock_movement`. Corrections are new reversing movements.
6. **Every movement links to a source document** (purchase, production run, dispatch, adjustment, credit note).
7. **Posted documents are never deleted.** Invoices are cancelled with a credit note; runs are reversed.
8. **Edits are audit-logged** (who, when, before → after) for invoices and production runs at minimum.
9. **Never commit secrets.** `.env` is git-ignored; only `.env.example` is tracked.
10. **Scope gate:** nothing beyond the "Must have" tier until `pytest -m benchmark` passes.
11. **Simple beats clever.** Add a dependency only if it removes real code or risk.

## 5. Repo etiquette

- Branches: `main` is always green. Work on `feat/<phase>-<topic>`, `fix/<topic>`, `docs/<topic>`.
- Small commits, one logical change each. Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`, `chore:`, `ci:` (optional scope, e.g. `feat(inventory): ...`).
- Tests (and lint) must pass before merge to `main`.
- After every milestone, run `/update-docs-and-commit`, which updates `docs/project_status.md`,
  `docs/changelog.md` and, if the design changed, `docs/architecture.md`.
- Never rewrite published history on `main`. Never `--no-verify`.
- Write the benchmark test first, then make it pass.

## 6. Commands

> Status: **planned**. These become real as phases land; update this block when they do.

| Task | Command |
| --- | --- |
| Setup (first time) | `cp .env.example .env` then `docker compose build` |
| Run everything | `docker compose up` (API on :8000, web on :5173) |
| DB migrate | `docker compose run --rm api alembic upgrade head` |
| Seed benchmark data | `docker compose run --rm api python -m app.seed` |
| Test (all) | `docker compose run --rm api pytest` |
| Benchmark only | `docker compose run --rm api pytest -m benchmark -v` |
| Lint backend | `docker compose run --rm api ruff check . && ruff format --check .` |
| Lint frontend | `cd frontend && npm run lint` |

## 7. Installation

Prerequisites: Git, Docker Desktop (with Compose v2). Optional for running without Docker: Python 3.12, Node 20+.

```bash
git clone https://github.com/preethi7711/factoryflow.git
cd factoryflow
cp .env.example .env        # then edit secrets
docker compose up --build
```

Test logins for each role are created by the seed script and listed in the README (dev-only passwords).

## 8. Working agreements for Claude

- Explain every non-obvious decision in plain language. The author must be able to defend it in an interview.
- Flag assumptions and record them in `docs/project_spec.md` → *Assumptions*.
- Ask before installing plugins or MCP servers, adding paid services, or pushing.
- Prefer editing existing files to creating new ones. Don't add docs nobody asked for.
