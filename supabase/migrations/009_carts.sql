-- Carts that outlive the call: one per interaction, for a restaurant, pharmacy or kirana alike.
--
-- ADDITIVE ONLY: one new table, new columns, a view and two functions. Nothing the running API uses is changed
-- except forget_customer, which now also clears the personal details on call orders and carts.
-- Run AFTER 008 and BEFORE deploying the new API. Safe to run twice. Undo: rollback/009_carts_down.sql
--
-- A cart's life:   open --(checkout)--> ordered
--                  open --(call ends or goes quiet, items inside)--> abandoned --(they order later)--> recovered
--                                                                              \--(window passes)--> expired
-- "abandoned" is still worth an outbound call; "expired" is closed and only counts in the drop-off numbers.

begin;

create table if not exists carts (
  id               uuid primary key default gen_random_uuid(),
  restaurant_id    uuid references restaurants (id) on delete cascade,   -- who sees it on their dashboard
  store_id         uuid references phone_stores (id) on delete set null, -- the number that was called
  interaction_id   text not null unique,       -- Samvaad's id for the call; the key every tool call arrives with
  call_id          uuid references phone_calls (id) on delete set null,
  customer_id      uuid references customers (id) on delete set null,
  customer_phone   text,                        -- +91..., the user ID
  customer_name    text,
  phone_verified   boolean not null default false,
  channel          text not null default 'call' check (channel in ('call', 'whatsapp', 'table', 'web')),
  language         text,
  items            jsonb not null default '[]',  -- same shape as orders.items, notes included
  total            numeric(10, 2) not null default 0 check (total >= 0),
  fulfilment       text check (fulfilment in ('delivery', 'pickup')),
  address          text,
  special_requests text,
  needs_pharmacist boolean not null default false,
  status           text not null default 'open'
                   check (status in ('open', 'ordered', 'abandoned', 'recovered', 'expired')),
  order_id         uuid references orders (id) on delete set null,
  opened_at        timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  closed_at        timestamptz,                 -- set when the cart can no longer change: ordered, recovered or expired
  closed_reason    text,                        -- 'ordered', 'empty', 'recovery_window_over', ...
  recovery_attempts int not null default 0,     -- outbound calls or messages tried
  last_recovery_at timestamptz,
  check (restaurant_id is not null or store_id is not null)
);

create index if not exists carts_board_idx    on carts (restaurant_id, status, last_activity_at desc);
create index if not exists carts_call_idx     on carts (call_id) where call_id is not null;
create index if not exists carts_phone_idx    on carts (customer_phone, status) where customer_phone is not null;
create index if not exists carts_sweep_idx    on carts (status, last_activity_at) where status in ('open', 'abandoned');

alter table carts enable row level security;
drop policy if exists carts_read on carts;
create policy carts_read on carts for select using (restaurant_id is not null and is_member(restaurant_id));

-- ---------------------------------------------------------------- phone_calls ----

alter table phone_calls
  add column if not exists interaction_id text,
  add column if not exists customer_id    uuid references customers (id) on delete set null,
  add column if not exists direction      text not null default 'inbound' check (direction in ('inbound', 'outbound')),
  add column if not exists end_reason     text;

create unique index if not exists phone_calls_interaction_idx on phone_calls (interaction_id) where interaction_id is not null;

-- ------------------------------------------------------------- the sweeper ----
-- Run every few minutes (the API does it from a background loop; pg_cron can call it too). It only moves
-- carts and calls forward and never deletes. Defaults: quiet for 10 minutes means abandoned; 24 hours after that, expired.

create or replace function close_stale_carts(
  p_quiet interval default interval '10 minutes',
  p_window interval default interval '24 hours'
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_abandoned int; v_empty int; v_expired int; v_calls int;
begin
  update carts set status = 'expired', closed_at = now(), closed_reason = 'empty'
  where status = 'open' and last_activity_at < now() - p_quiet and jsonb_array_length(items) = 0;
  get diagnostics v_empty = row_count;

  update carts set status = 'abandoned', closed_reason = 'no_order'
  where status = 'open' and last_activity_at < now() - p_quiet and jsonb_array_length(items) > 0;
  get diagnostics v_abandoned = row_count;

  update carts set status = 'expired', closed_at = now(), closed_reason = 'recovery_window_over'
  where status = 'abandoned' and last_activity_at < now() - p_window;
  get diagnostics v_expired = row_count;

  -- A call whose "ended" message never arrived: settle it from what actually happened.
  update phone_calls c set
    ended_at = coalesce(c.ended_at, now()),
    outcome = case when exists (select 1 from orders o where o.call_id = c.id) then 'ordered' else 'abandoned' end
  where c.outcome = 'in_progress' and c.started_at < now() - interval '2 hours';
  get diagnostics v_calls = row_count;

  return jsonb_build_object('abandoned', v_abandoned, 'emptied', v_empty, 'expired', v_expired, 'calls_settled', v_calls);
end $$;

revoke all on function close_stale_carts(interval, interval) from public, anon, authenticated;
grant execute on function close_stale_carts(interval, interval) to service_role;

-- ------------------------------------------------------------------ funnel ----
-- Calls, orders and drop-offs per number per day (India time). security_invoker: it shows only what the
-- reader may read, and nobody but the backend can read the tables underneath.

create or replace view call_funnel with (security_invoker = true) as
select
  c.store_id,
  (c.started_at at time zone 'Asia/Kolkata')::date                            as day,
  count(distinct c.id)                                                         as calls,
  count(distinct c.id) filter (where c.outcome = 'ordered')                    as ordered,
  count(distinct c.id) filter (where c.outcome = 'callback')                   as callbacks,
  count(distinct c.id) filter (where c.outcome in ('abandoned', 'in_progress')) as no_order,
  count(distinct ct.id) filter (where ct.status in ('abandoned', 'expired') and coalesce(ct.closed_reason, '') <> 'empty') as dropped_carts,
  coalesce(sum(ct.total) filter (where ct.status in ('abandoned', 'expired') and coalesce(ct.closed_reason, '') <> 'empty'), 0) as dropped_value
from phone_calls c
left join carts ct on ct.call_id = c.id
group by c.store_id, (c.started_at at time zone 'Asia/Kolkata')::date;

revoke all on call_funnel from public, anon, authenticated;
grant select on call_funnel to service_role;

-- ---------------------------------------------------------- forget_customer ----
-- Same as before, plus: the name, number and address left on call orders and carts are cleared too (the
-- 002 version only cleared caller_phone and address_snapshot). Orders themselves stay for the owner's accounts.

create or replace function forget_customer(p_restaurant_id uuid, p_phone text)
returns void
language plpgsql security definer set search_path = public as $$
declare
  v_digits text := ltrim(p_phone, '+');   -- orders written by the phone path hold 91..., not +91...
begin
  update orders set customer_id = null, caller_phone = null, address_snapshot = null,
                    customer_phone = null, customer_name = null, address = null
  where restaurant_id = p_restaurant_id
    and (caller_phone = p_phone or customer_phone in (p_phone, v_digits) or customer_id in (
      select id from customers where restaurant_id = p_restaurant_id and phone = p_phone));

  update carts set customer_id = null, customer_phone = null, customer_name = null, address = null
  where restaurant_id = p_restaurant_id
    and (customer_phone in (p_phone, v_digits) or customer_id in (
      select id from customers where restaurant_id = p_restaurant_id and phone = p_phone));

  delete from customers where restaurant_id = p_restaurant_id and phone = p_phone;
end $$;

revoke all on function forget_customer(uuid, text) from public, anon, authenticated;

commit;
