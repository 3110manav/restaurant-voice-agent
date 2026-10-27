-- Sarthi multi-restaurant schema — Phase 1 DRAFT for review. NOT applied anywhere yet.
--
-- Builds on supabase/schema.sql (the existing `orders` and `requests` tables, which
-- this migration extends rather than replaces). Run in the Supabase SQL editor once
-- approved. Deliberately NOT in this phase: menu_imports (Phase 2, Excel/image
-- review staging), pos_connections (Phase 4), add-ons (additive later).

create extension if not exists vector;

-- ---------------------------------------------------------------- tenancy ----

create table restaurants (
  id           uuid primary key default gen_random_uuid(),
  slug         text not null unique
               check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),       -- public URL: /r/{slug}
  name         text not null,
  cuisine      text,                                            -- "Punjabi", "Multi-cuisine fine dine"
  tagline      text,
  agent_name   text not null default 'Kabir',                   -- the waiter's name for this restaurant
  currency     text not null default 'INR',
  accent_color text,
  logo_url     text,
  status       text not null default 'live' check (status in ('draft', 'live')),
  -- Bumped on every menu write so any backend instance can tell its cached copy of
  -- this restaurant's menu is stale with one cheap read.
  menu_version bigint not null default 0,
  created_at   timestamptz not null default now()
);

-- Which logged-in users belong to which restaurant, and in what role.
create table restaurant_members (
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  role          text not null default 'owner' check (role in ('owner', 'manager', 'staff')),
  created_at    timestamptz not null default now(),
  primary key (restaurant_id, user_id)
);
create index restaurant_members_user_idx on restaurant_members (user_id);

-- ------------------------------------------------------------------- menu ----

create table menu_categories (
  id            uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  name          text not null,
  sort_order    int not null default 0,
  unique (restaurant_id, name)
);

create table dishes (
  id                uuid primary key default gen_random_uuid(),
  restaurant_id     uuid not null references restaurants (id) on delete cascade,
  category_id       uuid references menu_categories (id) on delete set null,
  name              text not null,
  price             numeric(10, 2) not null check (price >= 0),  -- cheapest variant's price when variants exist
  is_veg            boolean not null default true,
  spice_level       text check (spice_level in ('none', 'mild', 'medium', 'hot')),
  is_available      boolean not null default true,              -- owner can "86" a dish instantly
  image_url         text,

  -- Two layers of dish knowledge (see the plan):
  short_description text not null default '',                   -- the card: used while ordering
  long_description  text not null default '',                   -- the story: taste, origin, how it's eaten
  ingredients       text[] not null default '{}',
  allergens         text[] not null default '{}',
  tags              text[] not null default '{}',               -- 'bestseller', 'jain', 'gluten-free', ...
  knowledge_status  text not null default 'missing'
                    check (knowledge_status in ('missing', 'ai_draft', 'approved')),

  pos_item_id       text,                                       -- the item's id in the restaurant's POS
  source            text not null default 'manual'
                    check (source in ('manual', 'excel', 'image', 'pos', 'starter')),
  sort_order        int not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (restaurant_id, name)
);
create index dishes_restaurant_idx on dishes (restaurant_id, category_id, sort_order);
create unique index dishes_pos_item_idx on dishes (restaurant_id, pos_item_id)
  where pos_item_id is not null;

-- Sizes/portions (Regular/Medium/Large, Half/Full). A dish with no rows here is
-- single-size and sells at dishes.price. restaurant_id is denormalized for RLS.
create table dish_variants (
  id             uuid primary key default gen_random_uuid(),
  dish_id        uuid not null references dishes (id) on delete cascade,
  restaurant_id  uuid not null references restaurants (id) on delete cascade,
  name           text not null,
  price          numeric(10, 2) not null check (price >= 0),
  pos_variant_id text,
  sort_order     int not null default 0,
  unique (dish_id, name)
);
create index dish_variants_restaurant_idx on dish_variants (restaurant_id, dish_id);

-- ------------------------------------------------------------- embeddings ----

-- One embedding per dish, 768 dims (Gemini embedding-001 supports reduced output).
-- `content_hash` is a hash of the text that was embedded: when an owner edits a dish,
-- only dishes whose hash changed are re-embedded (today's whole-catalog hash can't do
-- that, which is why adding one dish currently means rebuilding everything).
-- No ANN index on purpose: an exact scan over one restaurant's few hundred rows takes
-- milliseconds and avoids the poor recall HNSW gives when filtering by restaurant.
create table dish_embeddings (
  dish_id       uuid primary key references dishes (id) on delete cascade,
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  embedding     vector(768) not null,
  content_hash  text not null,
  model         text not null default 'gemini-embedding-001',
  updated_at    timestamptz not null default now()
);
create index dish_embeddings_restaurant_idx on dish_embeddings (restaurant_id);

-- The agent's search_menu tool calls this; the backend then loads the matched dishes.
create function match_dishes(p_restaurant_id uuid, p_query vector(768), p_limit int default 4)
returns table (dish_id uuid, similarity float)
language sql stable set search_path = public, extensions as $$
  select e.dish_id, 1 - (e.embedding <=> p_query) as similarity
  from dish_embeddings e
  join dishes d on d.id = e.dish_id
  where e.restaurant_id = p_restaurant_id and d.is_available
  order by e.embedding <=> p_query
  limit p_limit;
$$;

-- ------------------------------------------- existing tables, now per-tenant ----

alter table orders
  add column restaurant_id uuid references restaurants (id) on delete set null,
  add column table_no      text,
  add column pos_order_id  text,            -- filled in by the POS adapter (Phase 4)
  add column pos_status    text,
  add column pos_synced_at timestamptz;

alter table requests
  add column restaurant_id uuid references restaurants (id) on delete set null,
  add column table_no      text;

create index orders_restaurant_idx   on orders   (restaurant_id, created_at desc);
create index requests_restaurant_idx on requests (restaurant_id, created_at desc);

-- ------------------------------------------------- atomic restaurant signup ----

-- Creates a restaurant and makes `p_owner` its owner in one transaction. Called only
-- by the backend (after verifying the owner's login), never directly by browsers.
create function create_restaurant(p_owner uuid, p_name text, p_slug text, p_cuisine text default null)
returns restaurants
language plpgsql security definer set search_path = public as $$
declare r restaurants;
begin
  insert into restaurants (name, slug, cuisine) values (p_name, p_slug, p_cuisine)
    returning * into r;
  insert into restaurant_members (restaurant_id, user_id, role) values (r.id, p_owner, 'owner');
  return r;
end $$;
revoke all on function create_restaurant(uuid, text, text, text) from public, anon, authenticated;

-- Atomic increment (a plain PostgREST update can't do `menu_version + 1`). Backend only.
create function bump_menu_version(p_restaurant_id uuid)
returns bigint
language sql security definer set search_path = public as $$
  update restaurants set menu_version = menu_version + 1
  where id = p_restaurant_id
  returning menu_version;
$$;
revoke all on function bump_menu_version(uuid) from public, anon, authenticated;

-- ---------------------------------------------------- row level security ----
-- The backend uses the service key (bypasses RLS), so these policies are defense in
-- depth: a leaked browser key, or a future direct-from-browser read, can only ever see
-- rows for restaurants the logged-in user belongs to. NOTE: the existing `orders` and
-- `requests` tables currently have RLS OFF — fixed here.

create function is_member(rid uuid, roles text[] default '{owner,manager,staff}')
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from restaurant_members
    where restaurant_id = rid and user_id = auth.uid() and role = any (roles)
  );
$$;

alter table restaurants        enable row level security;
alter table restaurant_members enable row level security;
alter table menu_categories    enable row level security;
alter table dishes             enable row level security;
alter table dish_variants      enable row level security;
alter table dish_embeddings    enable row level security;
alter table orders             enable row level security;
alter table requests           enable row level security;

create policy restaurants_read   on restaurants for select using (is_member(id));
create policy restaurants_update on restaurants for update using (is_member(id, '{owner,manager}'));

create policy members_read on restaurant_members for select
  using (user_id = auth.uid() or is_member(restaurant_id, '{owner}'));

create policy categories_read  on menu_categories for select using (is_member(restaurant_id));
create policy categories_write on menu_categories for all
  using (is_member(restaurant_id, '{owner,manager}'))
  with check (is_member(restaurant_id, '{owner,manager}'));

create policy dishes_read  on dishes for select using (is_member(restaurant_id));
create policy dishes_write on dishes for all
  using (is_member(restaurant_id, '{owner,manager}'))
  with check (is_member(restaurant_id, '{owner,manager}'));

create policy variants_read  on dish_variants for select using (is_member(restaurant_id));
create policy variants_write on dish_variants for all
  using (is_member(restaurant_id, '{owner,manager}'))
  with check (is_member(restaurant_id, '{owner,manager}'));

create policy embeddings_read on dish_embeddings for select using (is_member(restaurant_id));

create policy orders_read    on orders   for select using (is_member(restaurant_id));
create policy requests_read  on requests for select using (is_member(restaurant_id));
create policy requests_close on requests for update using (is_member(restaurant_id));
