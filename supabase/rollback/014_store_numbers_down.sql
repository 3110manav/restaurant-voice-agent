-- Undo 014_store_numbers.sql. Calls then route by phone_stores.phone_number alone (one number per restaurant):
-- any extra numbers added since are lost.
begin;
alter table phone_calls drop column if exists called_number;
drop table if exists store_numbers;
commit;
