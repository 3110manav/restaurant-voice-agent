-- The number mapper: which dialled number belongs to which restaurant (phone store).
--
-- One Samvaad agent answers every restaurant. At the start of a call it sends us the number the guest dialled
-- (called_number); this table says whose number that is, and the agent becomes that restaurant for the call.
-- A restaurant can have several numbers (a new line, its old number forwarded, a second outlet's line); a number
-- belongs to exactly one restaurant.
--
-- ADDITIVE ONLY. phone_stores.phone_number stays and keeps working (it is copied in here, and read as a fallback),
-- so the running API is unaffected before, during and after this runs. Safe to run twice.
-- Undo: supabase/rollback/014_store_numbers_down.sql

begin;

create table if not exists store_numbers (
  id         uuid primary key default gen_random_uuid(),
  number     text not null unique check (number ~ '^\+[0-9]{8,15}$'),   -- +91..., as numbers.canonical() writes it
  store_id   uuid not null references phone_stores (id) on delete cascade,
  label      text,                                                        -- "main line", "old number, forwarded"
  created_at timestamptz not null default now()
);
create index if not exists store_numbers_store_idx on store_numbers (store_id);

-- Backend only: no policies, so nobody but the service role can read or change the routing.
alter table store_numbers enable row level security;

insert into store_numbers (number, store_id, label)
select phone_number, id, 'main line' from phone_stores
where phone_number is not null and phone_number ~ '^\+[0-9]{8,15}$'
on conflict (number) do nothing;

-- Which number each call came in on, so a call that reached the wrong restaurant can be explained.
alter table phone_calls add column if not exists called_number text;

commit;
