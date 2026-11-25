-- Each restaurant's own rule book for the voice agent: the edge cases only that restaurant has ("pasta comes in
-- penne or spaghetti", "no delivery beyond 5 km", "sizzlers take 25 minutes"). The owner writes it in the dashboard;
-- every Samvaad call receives it at the start (the house_rules variable) and the agent follows it, within the
-- ordering rules the backend enforces (prices, cart, read-back, checkout never move to the rule book).
--
-- ADDITIVE ONLY: two new columns with defaults. The running API ignores them until the new version is deployed.
-- Safe to run twice. Undo: supabase/rollback/010_agent_rules_down.sql

begin;

alter table restaurants
  add column if not exists agent_rules            text not null default '',
  add column if not exists agent_rules_updated_at timestamptz;

do $$ begin
  alter table restaurants add constraint restaurants_agent_rules_length check (char_length(agent_rules) <= 2000);
exception when duplicate_object then null;
end $$;

commit;
