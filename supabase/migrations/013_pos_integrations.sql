-- POS integrations (Petpooja first): one row per restaurant per POS environment, holding what we need to read that
-- restaurant's menu from the POS and to push orders into it.
--
-- Secrets: app_key / app_secret / access_token are ENCRYPTED by the backend (AES-256-GCM, app/pos/crypto.py) before
-- they reach this table, because we have to send them back to Petpooja on every call. Only the backend holds the
-- key (POS_ENCRYPTION_KEY on Render), so a leaked database dump alone doesn't leak working credentials. The webhook
-- token is the opposite case: Petpooja sends it to us and we only ever compare it, so only its SHA-256 is stored.
-- The *_hint columns keep the last 4 characters so a person can tell which credential is saved without seeing it.
--
-- Nothing in the browser may read this table: RLS is on with no policies, and anon/authenticated lose all
-- privileges. Only the backend's service key reaches it.
--
-- ADDITIVE ONLY. Run once in the Supabase SQL editor; safe to re-run.
-- Rollback: supabase/rollback/013_pos_integrations_down.sql

begin;

create table if not exists pos_integrations (
  id                  uuid primary key default gen_random_uuid(),
  restaurant_id       uuid not null references restaurants (id) on delete cascade,
  provider            text not null check (provider in ('petpooja')),
  environment         text not null check (environment in ('sandbox', 'production')),
  -- Petpooja's restaurant id / menu-sharing "mapping code" (sent as restID on every order). Stored readable:
  -- inbound webhooks name the restaurant by it, so it has to be looked up.
  pos_restaurant_id   text not null check (length(trim(pos_restaurant_id)) > 0),

  app_key_enc         text not null,
  app_key_hint        text not null default '',
  app_secret_enc      text not null,
  app_secret_hint     text not null default '',
  access_token_enc    text not null,
  access_token_hint   text not null default '',
  credentials_updated_at timestamptz not null default now(),

  webhook_token_hash  text not null,                -- sha256 hex of the token Petpooja sends us
  webhook_token_hint  text not null default '',

  -- draft: credentials saved; menu_synced: first menu received; live: orders are relayed; paused: relay switched off.
  status              text not null default 'draft' check (status in ('draft', 'menu_synced', 'live', 'paused')),
  -- Per-restaurant order defaults for the relay (packing charge, GST liability, ...). Filled in a later part.
  settings            jsonb not null default '{}'::jsonb,
  notes               text not null default '',
  last_menu_sync_at   timestamptz,
  last_error          text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  unique (restaurant_id, provider, environment),
  unique (provider, environment, pos_restaurant_id)
);

create index if not exists pos_integrations_restaurant_idx on pos_integrations (restaurant_id);

-- Who changed what, without the values: "credentials rotated", "status live -> paused", ...
create table if not exists pos_integration_events (
  id             uuid primary key default gen_random_uuid(),
  integration_id uuid not null references pos_integrations (id) on delete cascade,
  kind           text not null,
  detail         jsonb not null default '{}'::jsonb,
  created_at     timestamptz not null default now()
);
create index if not exists pos_integration_events_idx on pos_integration_events (integration_id, created_at desc);

alter table pos_integrations       enable row level security;
alter table pos_integration_events enable row level security;
revoke all on pos_integrations       from anon, authenticated;
revoke all on pos_integration_events from anon, authenticated;

commit;
