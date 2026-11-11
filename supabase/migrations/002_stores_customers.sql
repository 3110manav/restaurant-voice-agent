-- Sarthi stores + customers — Phase 2 DRAFT for review. NOT applied anywhere yet.
--
-- Run in the Supabase SQL editor after 001_multi_restaurant.sql. Safe to run on the live
-- database: it only adds columns/tables, and every existing restaurant keeps working
-- unchanged (business_type defaults to 'restaurant').
--
-- What this adds:
--   1. A store can be a restaurant, a kirana (general store) or a pharmacy. The table stays
--      called `restaurants` (renaming it would touch every query for no benefit today); the
--      new `business_type` column says what kind of store a row is. `dishes` is the generic
--      item table for all three.
--   2. Medicine details, 1:1 with a dish row, for pharmacies.
--   3. Customers, keyed by the caller's phone number, per store: one store never sees
--      another store's customers. Plus their delivery addresses.
--   4. Orders remember who ordered, how it is fulfilled, and where it goes.

-- ------------------------------------------------------------- store types ----

alter table restaurants
  add column business_type text not null default 'restaurant'
  check (business_type in ('restaurant', 'kirana', 'pharmacy'));

-- Groceries and medicines are not "veg" or "non-veg": allow NULL (the default stays true so
-- restaurant dishes created without a value behave as before).
alter table dishes alter column is_veg drop not null;
alter table dishes add column brand text;

-- ------------------------------------------------------------------ medicine ----

-- One row per medicine dish. `uses` and `symptoms` are what the agent searches and says
-- ("commonly used for ..."); the agent never gives doses. rx_required items are sold only
-- after the pharmacist verifies a prescription. Schedule X is deliberately not allowed.
create table medicine_info (
  dish_id       uuid primary key references dishes (id) on delete cascade,
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  generic_name  text,
  strength      text,
  form          text,
  rx_required   boolean not null default false,
  schedule      text check (schedule in ('H', 'H1')),
  uses          text[] not null default '{}',
  symptoms      text[] not null default '{}',
  precautions   text not null default '',
  reviewed_by   text,                         -- the pharmacist who approved this text
  reviewed_at   timestamptz,
  check (schedule is null or rx_required)     -- a scheduled drug always needs a prescription
);
create index medicine_info_restaurant_idx on medicine_info (restaurant_id);

-- --------------------------------------------------------------- customers ----

create table customers (
  id            uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  phone         text not null check (phone ~ '^\+[1-9][0-9]{7,14}$'),   -- E.164, e.g. +919876543210
  name          text,
  language      text not null default 'en' check (language in ('en', 'hi')),
  created_at    timestamptz not null default now(),
  unique (restaurant_id, phone)
);

create table customer_addresses (
  id            uuid primary key default gen_random_uuid(),
  customer_id   uuid not null references customers (id) on delete cascade,
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  line          text not null,                -- the full address, as confirmed on the call
  area          text,                         -- short locality, the only part the agent says aloud
  landmark      text,
  pincode       text check (pincode is null or pincode ~ '^[0-9]{6}$'),
  is_default    boolean not null default true,
  created_at    timestamptz not null default now()
);
create unique index customer_default_address_idx on customer_addresses (customer_id) where is_default;
create index customer_addresses_restaurant_idx on customer_addresses (restaurant_id);

-- -------------------------------------------------------------------- orders ----

alter table orders
  add column customer_id      uuid references customers (id) on delete set null,
  add column caller_phone     text,
  add column fulfilment       text check (fulfilment in ('dine_in', 'delivery', 'pickup')),
  add column address_snapshot jsonb,           -- the address as it was at order time
  add column needs_pharmacist boolean not null default false;   -- an Rx item is in the order

create index orders_customer_idx on orders (customer_id, created_at desc);

-- ---------------------------------------------------- recognising a caller ----

-- Everything the agent needs at the start of a call, in ONE round trip: who the caller is,
-- their saved address, how many orders they have placed and what the last one was. Returns
-- NULL for a number this store has never seen. Backend only.
create function customer_context(p_restaurant_id uuid, p_phone text)
returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'customer', jsonb_build_object('id', c.id, 'name', c.name, 'language', c.language, 'phone', c.phone),
    'address', (
      select jsonb_build_object('id', a.id, 'line', a.line, 'area', a.area, 'landmark', a.landmark, 'pincode', a.pincode)
      from customer_addresses a where a.customer_id = c.id
      order by a.is_default desc, a.created_at desc limit 1
    ),
    'order_count', (select count(*) from orders o where o.customer_id = c.id),
    'last_order', (
      select jsonb_build_object('items', o.items, 'created_at', o.created_at)
      from orders o where o.customer_id = c.id order by o.created_at desc limit 1
    )
  )
  from customers c
  where c.restaurant_id = p_restaurant_id and c.phone = p_phone;
$$;
revoke all on function customer_context(uuid, text) from public, anon, authenticated;

-- Deleting a customer on request: their profile and addresses go (cascade), and the personal
-- details left on their past orders are blanked, while the orders themselves stay for accounts.
create function forget_customer(p_restaurant_id uuid, p_phone text)
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

-- ---------------------------------------------------- row level security ----
-- Same stance as 001: the backend uses the service key, so these are defense in depth. A
-- store's staff can read their own customers; only the backend writes them.

alter table medicine_info      enable row level security;
alter table customers          enable row level security;
alter table customer_addresses enable row level security;

create policy medicine_read  on medicine_info for select using (is_member(restaurant_id));
create policy medicine_write on medicine_info for all
  using (is_member(restaurant_id, '{owner,manager}'))
  with check (is_member(restaurant_id, '{owner,manager}'));

create policy customers_read  on customers          for select using (is_member(restaurant_id));
create policy addresses_read  on customer_addresses for select using (is_member(restaurant_id));
