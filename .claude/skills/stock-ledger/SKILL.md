---
name: stock-ledger
description: Rules for any code that changes or reads stock. Covers the stock_movement ledger, lots/batches, unit conversion, weighted-average cost, production issues/output, dispatch, reversals and reconciliation. Use when touching backend/app/inventory, production, purchasing, sales dispatch, credit notes, or stock reports.
---

# Stock ledger rules

Design source: docs/architecture.md (sections 3–5). Expected numbers: docs/project_spec.md (section 4). Don't restate them; follow them.

## Hard rules (a violation is a bug, not a style issue)
1. **Only `inventory.service.post_movements()` inserts into `stock_movement`.** Other modules call it. No `session.add(StockMovement(...))` anywhere else.
2. **Never UPDATE or DELETE a movement.** The DB trigger enforces it. Never disable it, even in tests. Correct mistakes by posting `REVERSAL` movements with `reverses_id` set.
3. **Every movement has** `item_id`, `lot_id`, `source_type`, `source_id` and `source_line_id`, all NOT NULL. If you can't name the source document, you're not allowed to post.
4. **Quantities are `Decimal`, stored in the item's base unit** (g, ml, pcs, pkt). Convert with `core.units.to_base()` at the edge (API input) and never again inside services. No `float()`, no `round()` on quantities.
5. **Values are `int` paise.** Issue value = `core.wac.issue_value(qty, bal_qty, bal_value)`, which does half-up rounding and has the **anti-drift rule**: an issue that empties stock takes all of the remaining value.
6. **One transaction per business event.** Lock the item rows (`SELECT … FOR UPDATE`), check that balance ≥ qty, post all movements, write the audit row, commit. A partial post must be impossible.
7. **Balances are never stored.** `balance(item, lot=None, as_of=None)` = `SUM(qty), SUM(value_paise)`. Any cache must pass `reconcile()`.
8. **Lots:** a receipt or run output creates a lot. Issues and dispatches take lots from `inventory.allocate(item, qty)` (FIFO by `received_at`; FEFO = change the sort key there only).
9. **Production:** issue the actual quantities (damaged packaging is included in the issue and recorded as `damaged_qty` for info). Output posts to a new FG lot at material cost. Overheads entered later post `COST_ADJUST` (qty 0) on that lot.

## Before you finish any stock change
- [ ] A test asserts the balance in base units **and** value in paise after the change.
- [ ] `reconcile()` returns `[]` and the orphan count is 0 in that test.
- [ ] Reversing the document restores the balance exactly (qty and value).
- [ ] No float literal or `float()` appears in the diff (`grep -n "float" backend/app`).

## Anti-patterns to reject
`item.stock -= qty` · `UPDATE stock_movement` · computing stock in the frontend · issuing in kg in one place and g in another · `Decimal(0.1)` (use `Decimal("0.1")`) · catching IntegrityError to "retry" a post.
