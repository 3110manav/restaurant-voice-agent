-- When a phone store takes orders. Outside these hours the agent takes no new order and says when it opens.
--
-- opening_hours, in Indian time, per day of the week ("mon".."sun") or "daily" for every day not listed:
--   {"daily": [["11:00", "23:30"]]}
--   {"daily": [["12:00", "15:30"], ["19:00", "01:00"]], "mon": []}     two sittings; closes after midnight; shut on Monday
-- A closing time earlier than the opening time means the next morning. Empty (null) means always open.
--
-- Set it with:  python -m app.phone.setup_store hours <slug> "11:00-23:30"
-- Run once in the Supabase SQL editor. Safe to re-run. Rollback: supabase/rollback/011_opening_hours_down.sql

alter table phone_stores add column if not exists opening_hours jsonb;
