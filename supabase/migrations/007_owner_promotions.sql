-- What the owner chooses to push, and whether the waiter pushes it.
--
-- Per dish:
--   is_bestseller  the owner marks it a bestseller (the waiter recommends these first when a guest asks what to try)
--   is_new         the owner marks it a new item (the waiter mentions it once, on the guest's first order)
--   promo_note     one line the owner wants said about it ("launched this week, made with a new tandoor marinade")
-- Per restaurant, three switches, all on by default; turning one off stops the waiter doing that, at once:
--   suggest_pairings     a side and a drink with the first order, a dessert at the end (the dishes in `pairs_with`)
--   promote_bestsellers  recommend the dishes marked bestseller
--   promote_new_items    mention the dishes marked new
--
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table dishes add column if not exists is_bestseller boolean not null default false;
alter table dishes add column if not exists is_new boolean not null default false;
alter table dishes add column if not exists promo_note text not null default '';

alter table restaurants add column if not exists suggest_pairings boolean not null default true;
alter table restaurants add column if not exists promote_bestsellers boolean not null default true;
alter table restaurants add column if not exists promote_new_items boolean not null default true;
