-- Sarthi WhatsApp — Phase 3 DRAFT for review. NOT applied anywhere yet.
--
-- Run in the Supabase SQL editor after 002_stores_customers.sql. Only adds tables and
-- columns (plus replacing forget_customer so it also clears WhatsApp messages); existing
-- data is untouched.
--
-- What this adds:
--   1. store_channels: which WhatsApp number belongs to which store, and who gets the alerts.
--      Moving a store to another number is a row edit (or a new row), not a code change.
--   2. whatsapp_messages: every message in and out. It dedupes Meta's webhook retries, tells us
--      whether a customer's 24-hour window is open (free text vs an approved template), and is
--      the audit trail for what the shop owner was told.
--   3. A short order code and a status trail on orders, for prescription orders.

-- Demo stores accept a caller's number typed into the website's "who's calling?" prompt, so a returning
-- customer can be tried in a browser. A typed number is NOT proof of who someone is, so a real store keeps
-- this off: it recognises people by caller ID on a real call, or by their WhatsApp number. Off by default.
alter table restaurants add column demo_mode boolean not null default false;
update restaurants set demo_mode = true
  where slug in ('saffron-table', 'sarson-da-khet', 'slice-station', 'gupta-general-store', 'care-plus-medicals');

create table store_channels (
  id              uuid primary key default gen_random_uuid(),
  restaurant_id   uuid not null references restaurants (id) on delete cascade,
  kind            text not null default 'whatsapp' check (kind in ('whatsapp')),
  -- Meta's id for the number (a long digit string, NOT the phone number). The webhook says which
  -- number a message was sent to by this id, which is how an inbound message finds its store.
  phone_number_id text not null unique,
  display_number  text,                                  -- +91..., for humans
  -- The NAME of the environment variable that holds this number's access token. Tokens are never
  -- stored in the database; a second number under another Meta account just names another variable.
  token_env       text not null default 'WHATSAPP_ACCESS_TOKEN',
  notify_numbers  text[] not null default '{}',          -- the owner(s): every new order
  rx_numbers      text[] not null default '{}',          -- the pharmacist(s): prescription orders; empty = notify_numbers
  enabled         boolean not null default true,
  created_at      timestamptz not null default now()
);
create index store_channels_restaurant_idx on store_channels (restaurant_id);

create table whatsapp_messages (
  id             uuid primary key default gen_random_uuid(),
  restaurant_id  uuid references restaurants (id) on delete cascade,
  channel_id     uuid references store_channels (id) on delete set null,
  direction      text not null check (direction in ('in', 'out')),
  peer           text not null,                          -- the other party, E.164
  wa_message_id  text,                                   -- Meta's message id (inbound: for dedupe)
  kind           text not null,                          -- text, template, image, ...
  body           text,
  order_id       uuid references orders (id) on delete set null,
  status         text not null default 'sent' check (status in ('received', 'sent', 'failed', 'logged')),
  error          text,
  created_at     timestamptz not null default now()
);
create unique index whatsapp_messages_wa_id_idx on whatsapp_messages (wa_message_id) where wa_message_id is not null;
create index whatsapp_messages_store_idx on whatsapp_messages (restaurant_id, created_at desc);
create index whatsapp_messages_peer_idx  on whatsapp_messages (restaurant_id, peer, direction, created_at desc);

-- A short, speakable code on each order ("K7M2P"): what the shop owner replies with
-- ("confirm K7M2P"), and what the customer is told.
alter table orders
  add column short_code text,
  add column rx_path    text check (rx_path in ('whatsapp', 'pharmacist'));
-- orders.status is free text; the values used are: placed (default), awaiting_prescription,
-- awaiting_pharmacist, prescription_received, confirmed, rejected, out_for_delivery.
create index orders_short_code_idx on orders (restaurant_id, short_code);

-- Deleting a customer on request now also removes their WhatsApp messages.
create or replace function forget_customer(p_restaurant_id uuid, p_phone text)
returns void
language plpgsql security definer set search_path = public as $$
begin
  update orders set customer_id = null, caller_phone = null, address_snapshot = null
  where restaurant_id = p_restaurant_id
    and (caller_phone = p_phone or customer_id in (
      select id from customers where restaurant_id = p_restaurant_id and phone = p_phone));
  delete from whatsapp_messages where restaurant_id = p_restaurant_id and peer = p_phone;
  delete from customers where restaurant_id = p_restaurant_id and phone = p_phone;
end $$;
revoke all on function forget_customer(uuid, text) from public, anon, authenticated;

alter table store_channels     enable row level security;
alter table whatsapp_messages  enable row level security;
create policy channels_read on store_channels    for select using (is_member(restaurant_id, '{owner,manager}'));
create policy messages_read on whatsapp_messages for select using (is_member(restaurant_id, '{owner,manager}'));
