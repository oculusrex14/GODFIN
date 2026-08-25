alter table public.licenses
  add column if not exists kind text not null default 'purchase';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'licenses_kind_check'
      and conrelid = 'public.licenses'::regclass
  ) then
    alter table public.licenses
      add constraint licenses_kind_check
      check (kind in ('purchase', 'owner_test'));
  end if;
end
$$;

create unique index if not exists licenses_one_active_owner_test_per_user_idx
  on public.licenses(user_id)
  where kind = 'owner_test' and status = 'active';

comment on column public.licenses.kind is
  'purchase licenses are backed by Stripe purchases; owner_test licenses are private, non-revenue test entitlements.';
