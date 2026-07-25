-- subscriptions.payment_method was a free-text copy of accounts.name, which made
-- renaming an account a two-table write that could half-fail. Link by id instead.
alter table public.subscriptions
  add column if not exists account_id uuid references public.accounts(id) on delete set null;

update public.subscriptions s
   set account_id = a.id
  from public.accounts a
 where a.user_id = s.user_id
   and a.name = s.payment_method
   and s.account_id is null;

create index if not exists subscriptions_account_id_idx on public.subscriptions(account_id);

-- names must be unique per user so the dropdown and chips can't show two "Chase Visa"
create unique index if not exists accounts_user_name_key
  on public.accounts(user_id, lower(name));

comment on column public.subscriptions.payment_method is
  'DEPRECATED as of v5.7 - superseded by account_id. Kept read-only for one release as a rollback path; do not write to it.';
