-- OPTIONAL data tidy-up after 008 and 009. It only fills in empty columns from what is already on each row;
-- it deletes nothing. Take a backup first, and read the preview counts (step 1) before running step 2.
--
-- Step 1: how many rows would change
select
  (select count(*) from orders where channel is null)                                         as orders_without_channel,
  (select count(*) from orders o where restaurant_id is null and store_id is not null
     and exists (select 1 from phone_stores s join restaurants r on r.slug = s.restaurant_slug where s.id = o.store_id)) as orders_missing_restaurant,
  (select count(*) from orders where customer_phone ~ '^91[6-9][0-9]{9}$')                    as phones_to_normalise;

-- Step 2: run these together
begin;

-- where the order came from, worked out from how it was made
update orders set channel = case
    when call_id is not null or session_id like 'samvaad:%' or session_id like 'livekit:%' or order_type is not null then 'call'
    when session_id like 'wa:%' then 'whatsapp'
    when table_no is not null then 'table'
    else 'web' end
where channel is null;

-- phone-path orders that were saved without their restaurant (so the owner never saw them)
update orders o set restaurant_id = r.id
from phone_stores s join restaurants r on r.slug = s.restaurant_slug
where o.restaurant_id is null and o.store_id = s.id;

-- one phone format everywhere: +91xxxxxxxxxx (customers already use it)
update orders set customer_phone = '+' || customer_phone where customer_phone ~ '^91[6-9][0-9]{9}$';

commit;
