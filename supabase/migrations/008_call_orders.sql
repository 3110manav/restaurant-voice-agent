-- Call orders: who ordered, what they asked for, and which call it came from.
--
-- ADDITIVE ONLY. Every change is a new nullable column, a new index, or a function replaced with the same
-- signature, so the API that is running today keeps working before, during and after this runs.
-- Run this BEFORE deploying the new API. Safe to run twice. Undo: supabase/migrations/rollback/008_call_orders_down.sql
--
-- Not touched: order_type / fulfilment / address / address_snapshot / caller_phone stay as they are. The
-- owner's board reads them through coalesce() instead, and they are retired in a later cleanup, once nothing
-- writes them any more.

begin;

-- ------------------------------------------------------------------- orders ----

alter table orders
  add column if not exists customer_name     text,     -- as the guest said it on the call; may be empty
  add column if not exists phone_verified    boolean not null default false,
                                                       -- true: the caller ID from the phone network; false: a number the guest told us
  add column if not exists channel           text check (channel in ('call', 'whatsapp', 'table', 'web')),
  add column if not exists special_requests  text;     -- order-level wishes ("deliver after 8"). Per-dish notes stay on items[].note

create index if not exists orders_channel_idx on orders (restaurant_id, channel, created_at desc);

-- ----------------------------------------------------------------- requests ----
-- A request is anything a customer asks for beyond a dish. It can now be tied to the order and the call it came from,
-- so the owner sees it next to that order instead of in a separate list.

alter table requests
  add column if not exists order_id    uuid references orders (id) on delete set null,
  add column if not exists call_id     uuid references phone_calls (id) on delete set null,
  add column if not exists customer_id uuid references customers (id) on delete set null;

create index if not exists requests_order_idx on requests (order_id) where order_id is not null;
create index if not exists requests_call_idx  on requests (call_id)  where call_id is not null;

-- ---------------------------------------------------------- place_phone_order ----
-- Every phone order is saved through this function. Same name, same arguments, same return: the new columns are
-- read from the payload and are NULL when an older API doesn't send them. Requests made earlier in the same
-- call are attached to the order once it exists.

create or replace function place_phone_order(p_order jsonb, p_messages jsonb) returns uuid
language plpgsql
as $$
declare
  v_id uuid := (p_order ->> 'id')::uuid;
  v_inserted int;
begin
  insert into orders (
    id, session_id, persona, items, total, restaurant_id, store_id, call_id,
    customer_phone, order_type, address, language, payment_ref, pay_token,
    customer_id, customer_name, phone_verified, channel, special_requests
  )
  values (
    v_id,
    p_order ->> 'session_id',
    p_order ->> 'persona',
    p_order -> 'items',
    (p_order ->> 'total')::numeric,
    (p_order ->> 'restaurant_id')::uuid,
    (p_order ->> 'store_id')::uuid,
    (p_order ->> 'call_id')::uuid,
    p_order ->> 'customer_phone',
    p_order ->> 'order_type',
    p_order ->> 'address',
    p_order ->> 'language',
    p_order ->> 'payment_ref',
    p_order ->> 'pay_token',
    (p_order ->> 'customer_id')::uuid,
    p_order ->> 'customer_name',
    coalesce((p_order ->> 'phone_verified')::boolean, false),
    coalesce(p_order ->> 'channel', 'call'),
    p_order ->> 'special_requests'
  )
  on conflict (id) do nothing;

  get diagnostics v_inserted = row_count;
  if v_inserted = 1 then
    insert into message_outbox (order_id, call_id, recipient, kind, body)
    select v_id, (p_order ->> 'call_id')::uuid, m ->> 'recipient', m ->> 'kind', m -> 'body'
    from jsonb_array_elements(p_messages) as m;

    if (p_order ->> 'call_id') is not null then
      update requests set order_id = v_id
      where call_id = (p_order ->> 'call_id')::uuid and order_id is null;
    end if;
  end if;
  return v_id;
end;
$$;

revoke all on function place_phone_order(jsonb, jsonb) from public, anon, authenticated;
grant execute on function place_phone_order(jsonb, jsonb) to service_role;

commit;
