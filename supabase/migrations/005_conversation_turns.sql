-- What guests and the agent said to each other, one row per turn, so an owner can read a conversation back
-- (the Conversations tab in the owner console) instead of it living only in a server log. Run once in the
-- Supabase SQL editor, after the earlier migrations.
--
-- A turn is what the agent received (the guest's typed words, or what speech recognition heard) and what it
-- answered. Rows hold what customers said, which can include names and addresses: only owners and managers
-- of the restaurant can read them.

create table if not exists conversation_turns (
  id            uuid primary key default gen_random_uuid(),
  restaurant_id uuid not null references restaurants (id) on delete cascade,
  session_id    text not null,           -- one guest's visit; typed chat and a call from the same page share it
  channel       text not null,           -- chat | push-to-talk | browser-call | phone | whatsapp
  speech        text,                    -- groq | sarvam, for voice turns
  language      text,
  table_no      text,
  caller_phone  text,                    -- when the agent knew who it was talking to
  customer_text text not null,
  agent_text    text not null,
  latency_ms    int,
  created_at    timestamptz not null default now()
);

create index if not exists conversation_turns_session_idx on conversation_turns (restaurant_id, session_id, created_at);
create index if not exists conversation_turns_recent_idx  on conversation_turns (restaurant_id, created_at desc);

-- The backend writes with the service key; this is defense in depth, as in the other tables.
alter table conversation_turns enable row level security;
drop policy if exists conversation_turns_read on conversation_turns;
create policy conversation_turns_read on conversation_turns for select using (is_member(restaurant_id, '{owner,manager}'));
