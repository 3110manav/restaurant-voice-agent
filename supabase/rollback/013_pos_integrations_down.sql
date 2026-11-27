-- Undo 013_pos_integrations.sql. Deletes every saved POS credential; restaurants, menus and orders are untouched.
begin;
drop table if exists pos_integration_events;
drop table if exists pos_integrations;
commit;
