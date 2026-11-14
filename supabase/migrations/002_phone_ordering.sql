-- Sarthi phone ordering: a customer calls a store, the agent takes the order, and the store and the
-- customer both get it on WhatsApp (the customer with a UPI QR). Run once in the Supabase SQL editor,
-- after schema.sql and 001_multi_restaurant.sql.

-- ------------------------------------------------------------------- stores ----

-- A business that answers phone calls. The dialled number picks the store. A kirana keeps its own
-- catalog here; a restaurant reads the menu it already has (restaurant_slug).
create table phone_stores (
  id              uuid primary key default gen_random_uuid(),
  slug            text not null unique,
  name            text not null,
  business_type   text not null check (business_type in ('kirana', 'restaurant')),
  agent_name      text not null,
  phone_number    text unique,                    -- the dialled number, +91...; null means not answering calls
  owner_whatsapp  text not null,                  -- digits with country code: 9198...
  upi_id          text not null,
  upi_payee_name  text not null,
  upi_is_merchant boolean not null default false, -- a merchant UPI ID can carry a transaction reference
  restaurant_slug text,
  catalog         jsonb,
  created_at      timestamptz not null default now(),
  check (
    (business_type = 'restaurant' and restaurant_slug is not null)
    or (business_type = 'kirana' and catalog is not null)
  )
);

-- -------------------------------------------------------------------- calls ----

create table phone_calls (
  id         uuid primary key default gen_random_uuid(),
  room       text not null unique,
  store_id   uuid not null references phone_stores (id) on delete cascade,
  caller     text,
  outcome    text not null default 'in_progress'
             check (outcome in ('in_progress', 'ordered', 'callback', 'abandoned')),
  turns      jsonb not null default '[]',          -- what was said, with response times
  metrics    jsonb not null default '[]',          -- speech timings from the voice pipeline
  started_at timestamptz not null default now(),
  ended_at   timestamptz
);
create index phone_calls_started_idx on phone_calls (started_at desc);

-- ------------------------------------------------------------------- orders ----

alter table orders
  add column store_id       uuid references phone_stores (id) on delete set null,
  add column call_id        uuid references phone_calls (id) on delete set null,
  add column customer_phone text,
  add column order_type     text check (order_type in ('delivery', 'pickup')),
  add column address        text,
  add column language       text,               -- the call's language, for messages to the customer
  add column payment_status text not null default 'unpaid' check (payment_status in ('unpaid', 'paid')),
  add column payment_ref    text unique,          -- the short code people read out
  add column pay_token      text unique;          -- the unguessable part of the pay link

create index orders_store_idx on orders (store_id, created_at desc);
create index orders_call_idx on orders (call_id);

-- ----------------------------------------------------------------- messages ----

-- Every WhatsApp message goes through this queue, so a failed send is retried and never loses an order.
create table message_outbox (
  id              uuid primary key default gen_random_uuid(),
  order_id        uuid references orders (id) on delete cascade,
  call_id         uuid references phone_calls (id) on delete cascade,
  recipient       text not null,
  kind            text not null,
  body            jsonb not null,
  status          text not null default 'pending' check (status in ('pending', 'sending', 'sent', 'failed')),
  attempts        int not null default 0,
  last_error      text,
  wa_message_id   text,
  delivery_status text,                           -- what WhatsApp later reports: delivered, read, failed
  next_attempt_at timestamptz not null default now(),
  claimed_at      timestamptz,
  created_at      timestamptz not null default now(),
  sent_at         timestamptz
);
create index message_outbox_due_idx on message_outbox (status, next_attempt_at);
create index message_outbox_order_idx on message_outbox (order_id);
create index message_outbox_call_idx on message_outbox (call_id);
create index message_outbox_wa_idx on message_outbox (wa_message_id);

-- Saves an order and its messages together, so an order can't exist without them being queued.
-- The caller picks the order's id, which makes a retry after a lost response safe.
create function place_phone_order(p_order jsonb, p_messages jsonb) returns uuid
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
    p_order ->> 'pay_token'
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

-- --------------------------------------------------------------------- RLS ----

-- No policies: only the backend's service key can reach these. They hold customers' phone numbers.
alter table phone_stores enable row level security;
alter table phone_calls enable row level security;
alter table message_outbox enable row level security;
