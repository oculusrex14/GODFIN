begin;
select plan(26);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values (
  '00000000-0000-0000-0000-000000000000',
  '66666666-6666-4666-8666-666666666666',
  'authenticated', 'authenticated', 'cashfree-owner@example.test', '',
  now(), now(), now(), '{}'::jsonb, '{}'::jsonb
);

select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_00000000-0000-4000-8000-000000000001',
    'cf_order_primary', 'cf_payment_primary', 'cf_customer_primary',
    '66666666-6666-4666-8666-666666666666', 'max', 999900, 'inr',
    'max', repeat('6', 64), '6666', 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null
  )$$,
  'A valid Cashfree purchase is provisioned'
);
select is(
  (select payment_provider from public.purchases where provider_order_id =
    'godfin_00000000-0000-4000-8000-000000000001'),
  'cashfree',
  'The purchase records Cashfree as its provider'
);
select is(
  (select status from public.licenses where key_hash = repeat('6', 64)),
  'active',
  'A verified Cashfree purchase activates its license'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.provision_cashfree_purchase(text,text,text,text,uuid,text,bigint,text,text,text,text,text,text,text,boolean,text)',
    'EXECUTE'
  ),
  'service_role can provision Cashfree purchases'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.provision_cashfree_purchase(text,text,text,text,uuid,text,bigint,text,text,text,text,text,text,text,boolean,text)',
    'EXECUTE'
  ),
  'anon cannot provision Cashfree purchases'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.record_cashfree_payment_event(text,text,text,text,text,text,text,bigint,text,text,text,text,timestamp with time zone)',
    'EXECUTE'
  ),
  'service_role can record Cashfree events'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.record_cashfree_payment_event(text,text,text,text,text,text,text,bigint,text,text,text,text,timestamp with time zone)',
    'EXECUTE'
  ),
  'anon cannot record Cashfree events'
);
select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_00000000-0000-4000-8000-000000000001',
    'cf_order_primary', 'cf_payment_primary', 'cf_customer_primary',
    '66666666-6666-4666-8666-666666666666', 'max', 999900, 'inr',
    'max', repeat('6', 64), '6666', 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null
  )$$,
  'Replaying purchase provisioning is safe'
);
select is(
  (select count(*) from public.purchases where payment_provider = 'cashfree'),
  1::bigint,
  'Replayed provisioning does not duplicate purchases'
);
select is(
  (select count(*) from public.licenses where key_hash = repeat('6', 64)),
  1::bigint,
  'Replayed provisioning does not duplicate licenses'
);

select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:auto-unrelated', 'AUTO_REFUND_STATUS_WEBHOOK', 'auto-unrelated',
    'godfin_00000000-0000-4000-8000-000000000001', 'other_payment',
    'auto-unrelated', null, 999900, 'inr', 'SUCCESS', 'duplicate attempt',
    repeat('1', 64), '2026-08-16T09:00:00Z'
  )$$,
  'An auto-refund for another payment attempt is recorded'
);
select is(
  (select purchase_id from public.payment_events where provider_event_id =
    'cashfree:auto-unrelated'),
  null::uuid,
  'An unrelated payment auto-refund is not mapped by order ID alone'
);
select is(
  (select status from public.licenses where key_hash = repeat('6', 64)),
  'active',
  'An unrelated auto-refund does not revoke the paid license'
);

select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:refund-partial', 'REFUND_STATUS_WEBHOOK', 'refund-partial',
    'godfin_00000000-0000-4000-8000-000000000001', 'cf_payment_primary',
    'refund-partial', null, 10000, 'inr', 'SUCCESS', 'partial refund',
    repeat('2', 64), '2026-08-16T10:00:00Z'
  )$$,
  'A Cashfree partial refund is recorded'
);
select is(
  (select status from public.licenses where key_hash = repeat('6', 64)),
  'suspended',
  'A partial Cashfree refund suspends the license'
);
select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:refund-partial', 'REFUND_STATUS_WEBHOOK', 'refund-partial',
    'godfin_00000000-0000-4000-8000-000000000001', 'cf_payment_primary',
    'refund-partial', null, 10000, 'inr', 'SUCCESS', 'partial refund',
    repeat('2', 64), '2026-08-16T10:00:00Z'
  )$$,
  'A duplicate Cashfree refund event is idempotent'
);
select is(
  (select count(*) from public.payment_events where provider_event_id =
    'cashfree:refund-partial'),
  1::bigint,
  'A duplicate Cashfree event is stored once'
);
select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:refund-rest', 'REFUND_STATUS_WEBHOOK', 'refund-rest',
    'godfin_00000000-0000-4000-8000-000000000001', 'cf_payment_primary',
    'refund-rest', null, 989900, 'inr', 'SUCCESS', 'remaining refund',
    repeat('3', 64), '2026-08-16T11:00:00Z'
  )$$,
  'A second refund completing the full amount is recorded'
);
select is(
  (select status from public.licenses where key_hash = repeat('6', 64)),
  'revoked',
  'A full Cashfree refund revokes the license'
);

select lives_ok(
  $$select * from public.provision_cashfree_purchase(
    'godfin_00000000-0000-4000-8000-000000000002',
    'cf_order_dispute', 'cf_payment_dispute', 'cf_customer_primary',
    '66666666-6666-4666-8666-666666666666', 'pro', 499900, 'inr',
    'pro', repeat('7', 64), '7777', 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null
  )$$,
  'A second Cashfree purchase is provisioned for dispute tests'
);
select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:dispute-open', 'DISPUTE_CREATED', 'dispute-primary',
    'godfin_00000000-0000-4000-8000-000000000002', 'cf_payment_dispute',
    null, 'dispute-primary', 499900, 'inr', 'CHARGEBACK_CREATED',
    'chargeback opened', repeat('4', 64), '2026-08-16T12:00:00Z'
  )$$,
  'A Cashfree dispute is recorded'
);
select is(
  (select status from public.licenses where key_hash = repeat('7', 64)),
  'suspended',
  'An open Cashfree dispute suspends the license'
);
select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:dispute-won', 'DISPUTE_CLOSED', 'dispute-primary',
    'godfin_00000000-0000-4000-8000-000000000002', 'cf_payment_dispute',
    null, 'dispute-primary', 499900, 'inr', 'CHARGEBACK_MERCHANT_WON',
    'merchant won', repeat('5', 64), '2026-08-16T13:00:00Z'
  )$$,
  'A merchant-won Cashfree dispute is recorded'
);
select is(
  (select status from public.licenses where key_hash = repeat('7', 64)),
  'active',
  'A merchant-won dispute restores the license'
);
select lives_ok(
  $$select public.record_cashfree_payment_event(
    'cashfree:dispute-stale-lost', 'DISPUTE_CLOSED', 'dispute-primary',
    'godfin_00000000-0000-4000-8000-000000000002', 'cf_payment_dispute',
    null, 'dispute-primary', 499900, 'inr', 'CHARGEBACK_MERCHANT_LOST',
    'stale result', repeat('8', 64), '2026-08-16T11:30:00Z'
  )$$,
  'An out-of-order Cashfree dispute event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('7', 64)),
  'active',
  'A stale dispute result cannot override the newer merchant-won result'
);

select * from finish();
rollback;
