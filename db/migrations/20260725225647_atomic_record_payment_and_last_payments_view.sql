-- The app read the newest 500 payments and picked the first per subscription, so a
-- rarely-paid subscription would eventually lose its "Last paid" line. This view
-- returns exactly one row per subscription, so no limit is needed.
-- security_invoker keeps RLS applied as the calling user.
create or replace view public.last_payments
with (security_invoker = true) as
select distinct on (subscription_id)
       subscription_id, amount, paid_on, created_at
  from public.payments
 order by subscription_id, paid_on desc, created_at desc;

grant select on public.last_payments to authenticated;
