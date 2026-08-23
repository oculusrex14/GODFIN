begin;
select plan(18);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values (
  '00000000-0000-0000-0000-000000000000',
  '77777777-7777-4777-8777-777777777777',
  'authenticated', 'authenticated', 'upgrade-owner@example.test', '',
  now(), now(), now(), '{}'::jsonb, '{}'::jsonb
);

select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_10000000-0000-4000-8000-000000000001',
    'cf_order_pro', 'cf_payment_pro', 'cf_customer_upgrade',
    '77777777-7777-4777-8777-777777777777', 'pro', 499900, 'inr',
    'pro', repeat('a', 64), 'AAAA', 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null, 'base', null
  )$$,
  'Free to Pro provisions a base lifetime license'
);
select is(
  (select tier from public.licenses where key_hash = repeat('a', 64)),
  'pro',
  'The base license starts on Pro'
);
select is(
  (select state_version from public.licenses where key_hash = repeat('a', 64)),
  1::bigint,
  'The base license starts at state version one'
);

select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_10000000-0000-4000-8000-000000000002',
    'cf_order_upgrade', 'cf_payment_upgrade', 'cf_customer_upgrade',
    '77777777-7777-4777-8777-777777777777', 'pro_to_max', 500000, 'inr',
    'max', null, null, 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null, 'upgrade',
    (select id from public.licenses where key_hash = repeat('a', 64))
  )$$,
  'Pro to Max upgrades the existing lifetime license in place'
);
select is(
  (select count(*) from public.licenses where user_id =
    '77777777-7777-4777-8777-777777777777'),
  1::bigint,
  'The upgrade does not create a second license'
);
select is(
  (select tier from public.licenses where key_hash = repeat('a', 64)),
  'max',
  'The same license becomes Max'
);
select is(
  (select state_version from public.licenses where key_hash = repeat('a', 64)),
  2::bigint,
  'Changing tier increments the signed-entitlement state version'
);
select is(
  (select count(*) from public.purchases where license_id =
    (select id from public.licenses where key_hash = repeat('a', 64))),
  2::bigint,
  'The purchase chain records both base and upgrade payments'
);
select is(
  (select upgrade_license_id from public.purchases where product_code = 'pro_to_max'),
  (select id from public.licenses where key_hash = repeat('a', 64)),
  'The upgrade is tied to the existing license identity'
);
select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_10000000-0000-4000-8000-000000000002',
    'cf_order_upgrade', 'cf_payment_upgrade', 'cf_customer_upgrade',
    '77777777-7777-4777-8777-777777777777', 'pro_to_max', 500000, 'inr',
    'max', null, null, 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null, 'upgrade',
    (select id from public.licenses where key_hash = repeat('a', 64))
  )$$,
  'Replaying the upgrade webhook is idempotent'
);
select is(
  (select count(*) from public.purchases where product_code = 'pro_to_max'),
  1::bigint,
  'A replay does not duplicate the upgrade purchase'
);
select throws_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_10000000-0000-4000-8000-000000000003',
    'cf_order_duplicate', 'cf_payment_duplicate', 'cf_customer_upgrade',
    '77777777-7777-4777-8777-777777777777', 'max', 999900, 'inr',
    'max', repeat('b', 64), 'BBBB', 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null, 'base', null
  )$$,
  'P0001',
  'A purchase license already exists for this account',
  'A second base license cannot bypass the upgrade path'
);

select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:upgrade-refund', 'REFUND_STATUS_WEBHOOK', 'upgrade-refund',
    'godfin_10000000-0000-4000-8000-000000000002', 'cf_payment_upgrade',
    'upgrade-refund', null, 500000, 'inr', 'SUCCESS', 'upgrade refunded',
    repeat('c', 64), '2026-08-23T20:00:00Z'
  )$$,
  'A completed upgrade refund is recorded'
);
select is(
  (select tier from public.licenses where key_hash = repeat('a', 64)),
  'pro',
  'Refunding only the Max upgrade downgrades to Pro'
);
select is(
  (select status from public.licenses where key_hash = repeat('a', 64)),
  'active',
  'The valid base Pro purchase remains active after upgrade refund'
);
select is(
  (select state_version from public.licenses where key_hash = repeat('a', 64)),
  3::bigint,
  'The downgrade increments the signed-entitlement state version'
);

select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:base-refund', 'REFUND_STATUS_WEBHOOK', 'base-refund',
    'godfin_10000000-0000-4000-8000-000000000001', 'cf_payment_pro',
    'base-refund', null, 499900, 'inr', 'SUCCESS', 'base refunded',
    repeat('d', 64), '2026-08-23T21:00:00Z'
  )$$,
  'A completed base refund is recorded'
);
select is(
  (select status from public.licenses where key_hash = repeat('a', 64)),
  'suspended',
  'Refunding the base while an upgrade chain exists suspends for owner review'
);

select * from finish();
rollback;
