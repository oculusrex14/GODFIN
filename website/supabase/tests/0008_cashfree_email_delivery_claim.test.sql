begin;
select plan(5);

select has_column(
  'public',
  'purchases',
  'email_claimed_at',
  'Purchases have a server-only email delivery lease'
);
select is(
  (select relrowsecurity from pg_class where oid = 'public.purchases'::regclass),
  true,
  'Purchase row-level security remains enabled'
);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values (
  '00000000-0000-0000-0000-000000000000',
  '88888888-8888-4888-8888-888888888888',
  'authenticated', 'authenticated', 'email-lease@example.test', '',
  now(), now(), now(), '{}'::jsonb, '{}'::jsonb
);

insert into public.purchases (
  checkout_session_id, user_id, product_code, amount_total, currency,
  payment_provider, provider_order_id
) values (
  'cashfree-email-lease',
  '88888888-8888-4888-8888-888888888888',
  'max', 999900, 'inr', 'cashfree', 'cashfree-email-lease'
);

with claimed as (
  update public.purchases
  set email_claimed_at = now()
  where provider_order_id = 'cashfree-email-lease'
    and email_sent_at is null
    and email_claimed_at is null
  returning id
)
select is(
  (select count(*) from claimed),
  1::bigint,
  'The first delivery worker acquires the lease'
);

with claimed as (
  update public.purchases
  set email_claimed_at = now()
  where provider_order_id = 'cashfree-email-lease'
    and email_sent_at is null
    and email_claimed_at is null
  returning id
)
select is(
  (select count(*) from claimed),
  0::bigint,
  'A concurrent delivery worker cannot acquire an active lease'
);

update public.purchases
set email_claimed_at = now() - interval '11 minutes'
where provider_order_id = 'cashfree-email-lease';

with claimed as (
  update public.purchases
  set email_claimed_at = now()
  where provider_order_id = 'cashfree-email-lease'
    and email_sent_at is null
    and (
      email_claimed_at is null
      or email_claimed_at < now() - interval '10 minutes'
    )
  returning id
)
select is(
  (select count(*) from claimed),
  1::bigint,
  'A crashed worker lease becomes safely retryable after ten minutes'
);

select * from finish();
rollback;
