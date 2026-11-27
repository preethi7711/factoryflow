-- ============================================================
-- FactoryFlow: Reset all data and re-seed from scratch
-- Run this in the Neon SQL Editor (or any Postgres client)
-- before recording your demo.
--
-- After running this SQL:
--   Live site (Render): redeploy the service once — it will
--     auto-seed because SEED_ON_START=1 is set.
--   Local Docker: run:
--     docker compose exec api python -m app.seed
-- ============================================================

-- Drop every table (CASCADE removes dependent rows automatically)
-- and reset all auto-increment sequences to 1.

TRUNCATE TABLE
    payment_allocation,
    payment,
    dispatch,
    credit_note,
    invoice_line,
    invoice,
    invoice_sequence,
    order_line,
    sales_order,
    idempotency_key,
    run_overhead,
    run_consumption,
    production_run,
    purchase_line,
    purchase,
    stock_movement,
    stock_lot,
    stock_adjustment_line,
    stock_adjustment,
    audit_log,
    bom_line,
    bom,
    item_unit,
    item,
    customer,
    supplier,
    company_settings,
    app_user
RESTART IDENTITY CASCADE;

-- ============================================================
-- Done. The database is now empty.
-- Trigger a Render redeploy (or run python -m app.seed locally)
-- to repopulate with fresh benchmark + demo data.
-- ============================================================
