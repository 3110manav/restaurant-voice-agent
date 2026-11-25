-- Undo 010_agent_rules.sql. Deletes every restaurant's rule book: export it first if it matters.
begin;
alter table restaurants drop constraint if exists restaurants_agent_rules_length;
alter table restaurants drop column if exists agent_rules_updated_at;
alter table restaurants drop column if exists agent_rules;
commit;
