  -- What goes with what, written on the dish itself so the waiter never has to guess.
--
--   pairs_with  the dishes (by exact name on the same menu) that complement this one, best first:
--               Paneer Tikka Dry -> Roti, Naan;  Chicken Dum Biryani -> Veg Raita, Boondi Raita.
--               The agent suggests these first, and the names are also part of the dish's embedding text,
--               so a search for "something to go with paneer tikka" finds them.
--   order_role  the part a dish plays in an order: food (a starter, main or biryani), side (bread, rice,
--               raita, salad, papad), drink or dessert. Null means "work it out from the menu section".
--
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table dishes add column if not exists pairs_with text[] not null default '{}';
alter table dishes add column if not exists order_role text
  check (order_role is null or order_role in ('food', 'side', 'drink', 'dessert'));
