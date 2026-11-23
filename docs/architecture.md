# Architecture: FactoryFlow

> **Status: provisional.** The tech stack and details are confirmed in the Phase 0 plan. This file records
> *how* the system works. *What* it must do is in [project_spec.md](project_spec.md).

## 1. Shape: modular monolith

One FastAPI process, one PostgreSQL database, one React PWA. Modules talk to each other through
`service.py` functions, never through each other's tables.

```
frontend (PWA) ──HTTP/JSON──> api (FastAPI) ──SQLAlchemy──> PostgreSQL
                               ├─ auth       users, roles, tokens
                               ├─ masters    items, products, customers, suppliers, BOM, price list
                               ├─ inventory  stock_movement ledger  ◄── the single source of stock truth
                               ├─ production runs, issues, output, variance
                               ├─ sales      orders, approval, dispatch
                               ├─ billing    invoices, credit notes, GST
                               ├─ payments   receipts, allocation, outstanding
                               ├─ costing    WAC, run cost, cost per packet
                               ├─ reports    registers, GST summary, ledger, exports
                               └─ audit      audit_log (who / when / before → after)
```

**Why not microservices:** one factory, about 20 users, and the stock ledger has to change in the same
transaction as invoices and runs. Splitting it would buy distributed transactions and add nothing.

## 2. Core rules (how invariants are enforced)

| Invariant | Mechanism |
| --- | --- |
| Stock derived from ledger | Balances = `SUM(qty)` over `stock_movement` per item (per lot later). No writable balance column. |
| Ledger append-only | Only `inventory.service.post_movements()` inserts. A DB trigger rejects UPDATE/DELETE. |
| Traceable | Each movement has `source_type` + `source_id` (+ line id). NOT NULL. |
| No negative stock | Checked inside the posting transaction with a row lock (`SELECT … FOR UPDATE` on the item). |
| Money exact | `BIGINT` paise. Python `int`. Tax and cost maths in pure functions with tests. |
| Quantities exact | `NUMERIC(18,3)` in base units; Python `Decimal`. |
| Posted docs immutable | Status machine (`draft → posted → cancelled`). Cancelling posts reversing movements and a credit note. |
| Audit | `audit.record(entity, id, before, after, user)` is called in the same transaction as the change. |

## 3. Sections to complete in the plan (Phase 0)

- Tech stack with justification, rejected alternatives and free hosting
- ER diagram (Mermaid)
- Unit conversion, WAC costing, variance, GST place-of-supply, offline sync and idempotency
- Benchmark test design
