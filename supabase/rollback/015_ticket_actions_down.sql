drop index if exists requests_open_tickets_idx;
create index if not exists requests_open_callbacks_idx
  on requests (restaurant_id, created_at desc) where type = 'callback' and status = 'open';
alter table requests drop column if exists resolution;
alter table requests drop column if exists activity;
alter table requests drop column if exists attempts;
alter table requests drop column if exists priority;
alter table requests drop column if exists category;
