-- Sarthi table QR pilot: each restaurant's brand settings, one row per guest table session (the
-- turn tracker, the bill, the rating) and the restaurant's own customer list. Run once in the
-- Supabase SQL editor, after schema.sql, 001_multi_restaurant.sql and 002_phone_ordering.sql.
-- Everything here is additive: nothing that runs today reads these columns or tables.

-- --------------------------------------------------------------- branding ----

alter table restaurants
  add column if not exists theme_mode      text not null default 'light'
                                           check (theme_mode in ('light', 'dark')),
  add column if not exists corner_style    text not null default 'soft'
                                           check (corner_style in ('sharp', 'soft', 'round')),
  add column if not exists heading_style   text not null default 'modern'
                                           check (heading_style in ('modern', 'classic', 'bold')),
  add column if not exists google_review_url text,
  -- The bill's UPI link pays the restaurant directly. A merchant UPI ID can carry a reference.
  add column if not exists upi_id          text,
  add column if not exists upi_payee_name  text,
  add column if not exists upi_is_merchant boolean not null default false,
  add column if not exists gst_rate        numeric(4, 2) not null default 5
                                           check (gst_rate >= 0 and gst_rate <= 28),
  -- Minutes per table before Sarthi, timed by hand before go-live: the report's "before" number.
  add column if not exists baseline_turn_minutes int check (baseline_turn_minutes > 0);

-- --------------------------------------------------------- table sessions ----

-- One guest session at one table: from the first scan to the paid bill. The five moments are the
-- turn tracker's; `ordered` is every round sent to the kitchen, which is what the bill adds up.
create table if not exists table_sessions (
  id                uuid primary key default gen_random_uuid(),
  restaurant_id     uuid not null references restaurants (id) on delete cascade,
  session_id        text not null,
  table_no          text,
  status            text not null default 'open' check (status in ('open', 'closed')),
  seated_at         timestamptz not null default now(),
  first_order_at    timestamptz,
  food_served_at    timestamptz,
  bill_requested_at timestamptz,
  paid_at           timestamptz,               -- set when staff confirm the payment
  payment_method    text check (payment_method in ('upi', 'counter')),
  rounds            int not null default 0,
  ordered           jsonb not null default '[]',
  bill_total        numeric(10, 2),
  people            int not null default 1 check (people between 1 and 50),
  upsell_total      numeric(10, 2) not null default 0, -- dishes added from a suggestion
  guest_name        text,
  guest_phone       text,
  rating            int check (rating between 1 and 5),
  feedback          text,
  unique (restaurant_id, session_id)
);
create index if not exists table_sessions_restaurant_idx on table_sessions (restaurant_id, seated_at desc);

-- -------------------------------------------------------------- customers ----

-- The restaurant's own list: a guest is added only when they give their number at the bill.
-- Offers go only to customers who turned them on (offers_opt_in), and they can turn them off.
create table if not exists customers (
  id             uuid primary key default gen_random_uuid(),
  restaurant_id  uuid not null references restaurants (id) on delete cascade,
  phone          text not null,
  name           text,
  offers_opt_in  boolean not null default false,
  visits         int not null default 1,
  first_seen_at  timestamptz not null default now(),
  last_visit_at  timestamptz not null default now(),
  unique (restaurant_id, phone)
);
create index if not exists customers_restaurant_idx on customers (restaurant_id, last_visit_at desc);

-- -------------------------------------------------------------------- RLS ----

-- The backend uses the service key; these policies are defense in depth, as in 001.
alter table table_sessions enable row level security;
alter table customers      enable row level security;

drop policy if exists table_sessions_read on table_sessions;
drop policy if exists customers_read on customers;
create policy table_sessions_read on table_sessions for select using (is_member(restaurant_id));
create policy customers_read      on customers      for select using (is_member(restaurant_id, '{owner,manager}'));
