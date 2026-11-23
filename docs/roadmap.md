# Roadmap

Priority-ordered. **Every phase:**
- runs on branch `feat/pN-<topic>`
- ends with green tests and lint
- removes the `xfail` markers for the benchmark checks it turns green, **in the same commit**
- finishes with `/update-docs-and-commit`, then a merge to `main`

If a phase might not fit in the remaining usage window, say so **before** starting it and split it.

## Phases

### Day 1: foundation → benchmark backend (≈7.25 h)

| # | Phase | Est. | Done when |
|---|---|---|---|
| P1 | Skeleton: compose (`db`, `api`), FastAPI app + `/api/v1/health`, config, Alembic, pytest + test DB, ruff, GitHub Actions CI, project hooks. **Benchmark test file with every check `xfail(strict=True)`** | 1.0 h | CI green; benchmark shows all xfail |
| P1b | **Early deploy**: multi-stage Dockerfile (build React → FastAPI serves `dist/`), placeholder web page, Render Free web service auto-deploying from `main`, Neon Free DB | 0.75 h | live URL shows `/api/v1/health` OK and the placeholder page |
| P2 | Core maths: `money`, `units`, `gst`, `wac`, `variance` (pure, unit-tested) | 1.0 h | unit tests green |
| P3 | Auth/RBAC + 6 seeded logins, masters (items, units, lots, BOM, customers, suppliers, price list), **ledger + trigger + post/balance/reconcile**, audit, seed script | 1.5 h | reconcile, orphan and RBAC checks green |
| P4 | Purchase + production run (issues, output lot, damaged, variance) + overheads + cost per packet | 1.5 h | B1–B6, B8, B9, B9b, B13 green |
| P5 | Orders (idempotent), approval + stock check + shortage, invoice (GST, FY numbering), dispatch | 1.5 h | B7, B10, B10b, B12, B12b green |

### Day 2: finish the benchmark → UI → deliverables (≈5.75 h)

| # | Phase | Est. | Done when |
|---|---|---|---|
| P6 | Payments + allocation + outstanding | 0.5 h | **B11 → all checks green (benchmark gate)** |
| P7 | Invoice PDF (fpdf2) + share link; reports: sales register, stock summary, stock ledger, production report; CSV/XLSX export | 1.25 h | report tests green |
| P8 | Frontend (thin): login per role, **salesman mobile order (<1 min) with minimal offline queue**, admin queue → approve → invoice → dispatch → payment, production run screen, stock screens | 3.0 h | scenario clickable end to end; offline replay test |
| P9 | README (stack, tiers, assumptions, benchmark table, logins, cold-start note), design note (≤2 pages), final deploy check, demo-video script | 1.0 h | evaluator can run it from the README alone |

**━━━━ CUT LINE 1: must-haves + benchmark green + deployed (≈13 h) ━━━━**

| P10 | Should-haves: GST summary (GSTR-1 B2B + HSN, GSTR-3B 3.1(a)), purchase register, collections + ageing, variance alert list, owner dashboard | 1.5 h |
|---|---|---|

**━━━━ CUT LINE 2 ━━━━**

| P11 | Stretch, in order: FEFO toggle · "make N batches" from shortages · reorder alerts · Tally CSV | as time allows |
|---|---|---|

If time is short, P8 shrinks to the salesman order and the admin approve/invoice/dispatch screens. Reports stay API + download.

### P1 details fixed in review
- **Hooks** (`.claude/settings.json`):
  - PreToolUse on `Edit|Write`: exit 2 (block) if the path is `docs/PROBLEM.md`, `.env`, `.env.local` or any `.env.*` **except** `.env.example`, which stays editable.
  - PostToolUse: `ruff format` + `ruff check --fix` on edited `.py` files.
- **Benchmark test:** `backend/tests/benchmark/test_section5.py`, marked `benchmark`.
  - It drives the HTTP API, logging in as the right role for each step.
  - One module-scoped fixture runs steps 1–9 on a fresh schema plus the seed. Each check B1–B13 (plus b-checks) is its own test, with the exact numbers from [project_spec.md §4](project_spec.md).

### P1b details
- The user creates the Render and Neon accounts (Claude does not create accounts). **At signup, confirm that no credit card is asked.** If one is, stop and fall back to local `docker compose` plus the demo video.
- `DATABASE_URL` and `JWT_SECRET_KEY` are set in the Render dashboard, never in the repo.
- **No keep-alive pings**: they would burn Neon's free compute hours. The README notes the ~1 min cold start.

## Wow factor (only after cut line 1; each ≤30 min, no schema change)
1. **Trace any number**: stock balance → ledger rows → source document.
2. **Reconcile button**: live proof that ledger = balances.
3. **Shortage → "make 1 batch"** hint on Distributor B (uses BOM yield).
4. **WhatsApp share**: `wa.me` link with the invoice PDF URL.
5. **Benchmark badge**: CI runs `pytest -m benchmark`; the README table is generated from its output.
6. **Audit diff view**: before → after for invoice and run edits.

## Teaching protocol (after every phase, about 10 min)
1. **Explain**: the module's purpose, the 3 files that matter, one trace (request → router → service → ledger).
2. **Five likely interview questions** with crisp answers.
3. **One practice change for the author to do alone** (examples below).
4. Append everything to `docs/interview_notes.md` (created in P1).

| Phase | Sample question | Practice change |
|---|---|---|
| P2 | Why paise and not float? Where exactly do you round? | Add an 18% GST rate with a test |
| P3 | What stops someone editing stock? | Add an `ADJUST` movement endpoint for stock-take differences |
| P4 | Why WAC over FIFO? How is variance flagged? | **Add Murukku 500 g sharing the same ingredient lines** |
| P5 | Same-state vs other-state tax? Double-tap offline? | Change the invoice prefix to include a branch code |
| P6 | How is outstanding derived? | Add a 61–90 day ageing bucket |
| P7 | How do the reports reconcile? | Add an HSN column to the sales register |
| P8 | How does offline sync avoid duplicates? | Show a "pending sync" count badge |
