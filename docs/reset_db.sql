-- ============================================================
-- FactoryFlow: Reset all data and re-seed from scratch
-- Run this in the Neon SQL Editor before recording your demo.
--
-- Why DROP SCHEMA instead of TRUNCATE:
--   The ledger tables (stock_movement, audit_log, payment_allocation
--   etc.) have append-only DB triggers that block TRUNCATE.
--   Dropping the schema removes the data AND the triggers in one go.
--   The Render deploy that follows re-runs Alembic migrations,
--   which recreates everything cleanly.
--
-- After running this SQL:
--   Go to Render dashboard → your service → Manual Deploy
--   → "Deploy latest commit"
--   The service will run migrations + seed automatically.
--   Wait ~60 seconds, then open the live site to verify.
-- ============================================================

-- Drop every table and trigger, then recreate an empty schema.
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- Restore default privileges so Postgres and your app user can use it.
GRANT ALL ON SCHEMA public TO PUBLIC;

-- ============================================================
-- Done. The schema is now completely empty.
-- Trigger a Render Manual Deploy to run migrations + seed.
-- ============================================================
