-- Undoes 009_carts.sql. Drops every saved cart, so use it only if the carts are not wanted.
begin;

-- forget_customer exactly as 002_stores_customers.sql defined it
create or replace function forget_customer(p_restaurant_id uuid, p_phone text)
returns void
language plpgsql security definer set search_path = public as $$
begin
  update orders set customer_id = null, caller_phone = null, address_snapshot = null
  where restaurant_id = p_restaurant_id
    and (caller_phone = p_phone or customer_id in (
      select id from customers where restaurant_id = p_restaurant_id and phone = p_phone));
  delete from customers where restaurant_id = p_restaurant_id and phone = p_phone;
end $$;
revoke all on function forget_customer(uuid, text) from public, anon, authenticated;

drop view if exists call_funnel;
drop function if exists close_stale_carts(interval, interval);

drop index if exists phone_calls_interaction_idx;
alter table phone_calls
  drop column if exists interaction_id,
  drop column if exists customer_id,
  drop column if exists direction,
  drop column if exists end_reason;

drop table if exists carts;

commit;
