-- Phone calls to the kirana and pharmacy stores that live in the shop database (002_stores_customers.sql).
-- Run after 002_phone_ordering.sql, 003_table_pilot.sql and the stores branch's 002 and 003 migrations.
--
-- A phone store of type kirana or pharmacy can now point at a store's items in the database
-- (restaurant_slug) instead of carrying its own catalog file. Those stores take UPI nowhere in the call
-- (the owner is alerted on WhatsApp by app/whatsapp), so the UPI fields become optional.

alter table phone_stores drop constraint if exists phone_stores_business_type_check;
alter table phone_stores drop constraint if exists phone_stores_check;

alter table phone_stores
  add constraint phone_stores_business_type_check
    check (business_type in ('kirana', 'restaurant', 'pharmacy')),
  add constraint phone_stores_check
    check (
      (business_type = 'restaurant' and restaurant_slug is not null)
      or (business_type = 'pharmacy' and restaurant_slug is not null)
      or (business_type = 'kirana' and (catalog is not null or restaurant_slug is not null))
    );

alter table phone_stores alter column upi_id drop not null;
alter table phone_stores alter column upi_payee_name drop not null;
