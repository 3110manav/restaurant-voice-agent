-- Sarthi "basic ERP" schema: finalized orders and ambient service/front-desk
-- requests, written by the Python backend (app/erp.py) as a durability layer
-- on top of the in-memory per-session cart/service log.
--
-- Run this once in the Supabase SQL editor (Project > SQL Editor > New query)
-- after creating the project, before setting SUPABASE_URL / SUPABASE_SERVICE_KEY
-- in .env.

create table if not exists orders (
  id uuid primary key default gen_random_uuid(),
  session_id text not null,
  persona text not null,
  items jsonb not null,
  total numeric(10, 2) not null,
  status text not null default 'placed',
  created_at timestamptz not null default now()
);

create table if not exists requests (
  id uuid primary key default gen_random_uuid(),
  session_id text not null,
  persona text not null,
  type text not null,
  details text,
  notes text,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index if not exists orders_created_at_idx on orders (created_at desc);
create index if not exists requests_created_at_idx on requests (created_at desc);
create index if not exists requests_status_idx on requests (status);
