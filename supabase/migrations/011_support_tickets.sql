-- Support tickets: when a caller asks for a person (request_callback) or their order couldn't be saved, a row in
-- `requests` with type 'callback' and status 'open' is the ticket. The owner sees it on the Callbacks tab, calls the
-- number back and marks it resolved. `requests` already has type, details, status, resolved_at, restaurant_id,
-- order_id, call_id and customer_id; this adds the number to call back (the WhatsApp number the guest gave, else the
-- caller ID), which the board shows masked until the owner presses Call.
--
-- Run once in the Supabase SQL editor. Safe to re-run. Rollback: supabase/rollback/011_support_tickets_down.sql

alter table requests add column if not exists customer_phone text;

create index if not exists requests_open_callbacks_idx
  on requests (restaurant_id, created_at desc) where type = 'callback' and status = 'open';
