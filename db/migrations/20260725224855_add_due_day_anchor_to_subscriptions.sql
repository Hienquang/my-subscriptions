-- Anchor day-of-month for monthly billing cycles.
-- Without it, clamping Jan 31 -> Feb 28 permanently ratchets the bill down to the
-- 28th. With it, Feb 28 advances back to Mar 31 as the user intended.
alter table public.subscriptions
  add column if not exists due_day smallint
  check (due_day is null or (due_day >= 1 and due_day <= 31));

update public.subscriptions
   set due_day = extract(day from next_due)::smallint
 where due_day is null and next_due is not null;

comment on column public.subscriptions.due_day is
  'Day of month the user intended for monthly cycles; addCycle() clamps to the last day of short months but always re-anchors here.';
