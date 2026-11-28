-- Support tickets, the full version: what the ticket is about, how urgent it is, and everything staff did on it.
--
--   category    complaint · refund · booking · order_status · order_change · speak_to_person · order_failed · other
--   priority    urgent | normal (urgent: wrong or missing food, allergy, an order that couldn't be saved…)
--   status      open → in_progress (someone is on it) → resolved; reopening sets it back to open
--   attempts    calls that went unanswered
--   activity    the ticket's history, oldest first: [{"at", "kind", "text", "by"}]
--   resolution  what was done, written when it is resolved
--
-- Tickets saved before this migration still show: a missing category reads as "speak_to_person", priority as normal.
-- Run once in the Supabase SQL editor, after 012. Safe to re-run. Rollback: supabase/rollback/015_ticket_actions_down.sql

alter table requests add column if not exists category   text;
alter table requests add column if not exists priority   text not null default 'normal';
alter table requests add column if not exists attempts   integer not null default 0;
alter table requests add column if not exists activity   jsonb not null default '[]';
alter table requests add column if not exists resolution text;

-- The open list on the Support tab: urgent first, then the longest wait.
drop index if exists requests_open_callbacks_idx;
create index if not exists requests_open_tickets_idx
  on requests (restaurant_id, priority, created_at) where type = 'callback' and status in ('open', 'in_progress');
