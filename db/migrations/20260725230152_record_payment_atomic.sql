-- Mark-paid used to be two round trips: insert the payment, then advance next_due.
-- If the second failed, the bill still read as due and could be paid twice.
-- One function, one transaction: either both land or neither does.
--
-- The cycle maths deliberately stays in the client (addCycle(), covered by
-- tests/test_logic.py) so there is exactly one implementation of it. This function
-- only guarantees atomicity, and takes the already-computed next date.
create or replace function public.record_payment(
  p_subscription_id uuid,
  p_amount          numeric,
  p_paid_on         date,
  p_next_due        date,
  p_deactivate      boolean default false
) returns public.subscriptions
language plpgsql
security invoker
set search_path = public
as $$
declare
  s   public.subscriptions;
  uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'Not signed in';
  end if;

  -- explicit rather than leaning on the column default, so the row is always
  -- attributable even if the default is ever changed
  insert into public.payments (user_id, subscription_id, amount, paid_on)
  values (uid, p_subscription_id, p_amount, p_paid_on);

  update public.subscriptions
     set next_due = case when p_deactivate then next_due else p_next_due end,
         active   = case when p_deactivate then false     else active   end
   where id = p_subscription_id
  returning * into s;

  -- no row visible under RLS: roll the payment back rather than orphan it
  if s.id is null then
    raise exception 'Subscription % not found', p_subscription_id;
  end if;
  return s;
end;
$$;

grant execute on function public.record_payment(uuid, numeric, date, date, boolean) to authenticated;
