-- Undoes 008_call_orders.sql. Run 009's rollback first if 009 was applied (it points at these columns).
-- Loses only what the new API wrote into the new columns (names, channel, special requests, request links).
begin;

-- the function exactly as 002_phone_ordering.sql defined it
create or replace function place_phone_order(p_order jsonb, p_messages jsonb) returns uuid
language plpgsql
as $$
declare
  v_id uuid := (p_order ->> 'id')::uuid;
  v_inserted int;
begin
  insert into orders (
    id, session_id, persona, items, total, restaurant_id, store_id, call_id,
    customer_phone, order_type, address, language, payment_ref, pay_token
  )
  values (
    v_id, p_order ->> 'session_id', p_order ->> 'persona', p_order -> 'items', (p_order ->> 'total')::numeric,
    (p_order ->> 'restaurant_id')::uuid, (p_order ->> 'store_id')::uuid, (p_order ->> 'call_id')::uuid,
    p_order ->> 'customer_phone', p_order ->> 'order_type', p_order ->> 'address', p_order ->> 'language',
    p_order ->> 'payment_ref', p_order ->> 'pay_token'
  )
  on conflict (id) do nothing;

  get diagnostics v_inserted = row_count;
  if v_inserted = 1 then
    insert into message_outbox (order_id, call_id, recipient, kind, body)
    select v_id, (p_order ->> 'call_id')::uuid, m ->> 'recipient', m ->> 'kind', m -> 'body'
    from jsonb_array_elements(p_messages) as m;
  end if;
  return v_id;
end;
$$;
revoke all on function place_phone_order(jsonb, jsonb) from public, anon, authenticated;
grant execute on function place_phone_order(jsonb, jsonb) to service_role;

drop index if exists requests_order_idx;
drop index if exists requests_call_idx;
alter table requests drop column if exists order_id, drop column if exists call_id, drop column if exists customer_id;

drop index if exists orders_channel_idx;
alter table orders
  drop column if exists customer_name,
  drop column if exists phone_verified,
  drop column if exists channel,
  drop column if exists special_requests;

commit;
