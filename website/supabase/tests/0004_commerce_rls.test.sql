begin;
select plan(33);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values
  (
    '00000000-0000-0000-0000-000000000000',
    '11111111-1111-1111-1111-111111111111',
    'authenticated', 'authenticated', 'owner-one@example.test', '',
    now(), now(), now(), '{}'::jsonb, '{}'::jsonb
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '22222222-2222-2222-2222-222222222222',
    'authenticated', 'authenticated', 'owner-two@example.test', '',
    now(), now(), now(), '{}'::jsonb, '{}'::jsonb
  );

select lives_ok(
  $$select * from public.provision_purchase(
    'cs_test_primary', 'pi_test_primary', 'ch_test_primary', 'cus_test_primary',
    '11111111-1111-1111-1111-111111111111', 'max', 999900, 'inr',
    'max', repeat('1', 64), '1111', 0, 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null
  )$$,
  'A valid paid purchase is provisioned once'
);

insert into public.licenses (
  user_id, tier, key_hash, key_last4, status, state_version
) values (
  '22222222-2222-2222-2222-222222222222',
  'pro', repeat('9', 64), '9999', 'active', 1
);
insert into public.purchases (
  checkout_session_id, user_id, product_code, amount_total, currency, status
) values (
  'cs_test_other_user',
  '22222222-2222-2222-2222-222222222222',
  'pro', 499900, 'inr', 'paid'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.verify_license(text,text,text,text,integer)',
    'EXECUTE'
  ),
  'service_role can verify a license'
);
select ok(
  not has_function_privilege(
    'anon', 'public.verify_license(text,text,text,text,integer)', 'EXECUTE'
  ),
  'anon cannot verify a license directly'
);
select ok(
  not has_function_privilege(
    'authenticated', 'public.verify_license(text,text,text,text,integer)', 'EXECUTE'
  ),
  'authenticated users cannot verify a license directly'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.record_payment_event(text,text,text,text,text,text,text,text,bigint,text,text,text,text,timestamp with time zone)',
    'EXECUTE'
  ),
  'service_role can record payment events'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.record_payment_event(text,text,text,text,text,text,text,text,bigint,text,text,text,text,timestamp with time zone)',
    'EXECUTE'
  ),
  'anon cannot record payment events'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.provision_purchase(text,text,text,text,uuid,text,bigint,text,text,text,text,bigint,text,text,text,boolean,text)',
    'EXECUTE'
  ),
  'service_role can provision purchases'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.provision_purchase(text,text,text,text,uuid,text,bigint,text,text,text,text,bigint,text,text,text,boolean,text)',
    'EXECUTE'
  ),
  'anon cannot provision purchases'
);

select set_config(
  'request.jwt.claim.sub',
  '11111111-1111-1111-1111-111111111111',
  true
);
set local role authenticated;
select is(
  (select count(*) from public.licenses),
  1::bigint,
  'An authenticated user sees only their license'
);
select is(
  (
    select count(*) from public.licenses
    where user_id = '22222222-2222-2222-2222-222222222222'
  ),
  0::bigint,
  'Another user license is hidden by RLS'
);
select is(
  (select count(*) from public.purchases),
  1::bigint,
  'An authenticated user sees only their purchase'
);
select is(
  (
    select count(*) from public.purchases
    where user_id = '22222222-2222-2222-2222-222222222222'
  ),
  0::bigint,
  'Another user purchase is hidden by RLS'
);
reset role;

select lives_ok(
  $$select public.record_payment_event(
    'evt_partial', 'refund.updated', 're_primary', null,
    'pi_test_primary', 'ch_test_primary', 're_primary', null,
    100, 'inr', 'succeeded', 'requested_by_customer', repeat('a', 64),
    '2026-08-11T10:00:00Z'
  )$$,
  'A partial refund event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('1', 64)),
  'suspended',
  'A partial refund suspends the license'
);
select is(
  (
    select previous_status from public.license_status_history
    where license_id = (select id from public.licenses where key_hash = repeat('1', 64))
    order by state_version desc limit 1
  ),
  'active',
  'Status history records the actual previous state'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_partial', 'refund.updated', 're_primary', null,
    'pi_test_primary', 'ch_test_primary', 're_primary', null,
    100, 'inr', 'succeeded', 'requested_by_customer', repeat('a', 64),
    '2026-08-11T10:00:00Z'
  )$$,
  'A duplicate Stripe event is idempotent'
);
select is(
  (select count(*) from public.payment_events where stripe_event_id = 'evt_partial'),
  1::bigint,
  'A duplicate event is stored only once'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_full', 'refund.updated', 're_primary', null,
    'pi_test_primary', 'ch_test_primary', 're_primary', null,
    999900, 'inr', 'succeeded', 'requested_by_customer', repeat('b', 64),
    '2026-08-11T11:00:00Z'
  )$$,
  'A later full-refund update is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('1', 64)),
  'revoked',
  'A full refund revokes the license'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_stale_failed', 'refund.failed', 're_primary', null,
    'pi_test_primary', 'ch_test_primary', 're_primary', null,
    999900, 'inr', 'failed', 'declined', repeat('c', 64),
    '2026-08-11T09:00:00Z'
  )$$,
  'An out-of-order stale refund event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('1', 64)),
  'revoked',
  'A stale event cannot restore a revoked license'
);
select is(
  (
    public.verify_license(
      repeat('1', 64), repeat('a', 64), 'test device', '1.0.0', 3
    )->>'code'
  ),
  'LICENSE_REVOKED',
  'A revoked license cannot mint a signed entitlement response'
);

select lives_ok(
  $$select * from public.provision_purchase(
    'cs_test_dispute', 'pi_test_dispute', 'ch_test_dispute', 'cus_test_dispute',
    '11111111-1111-1111-1111-111111111111', 'pro', 499900, 'inr',
    'pro', repeat('2', 64), '2222', 0, 'IN', 'IN',
    'world-bank-icp-2021-v1', true, null
  )$$,
  'A second valid paid purchase is provisioned'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_dispute_open', 'charge.dispute.created', 'dp_test', null,
    'pi_test_dispute', 'ch_test_dispute', null, 'dp_test',
    499900, 'inr', 'needs_response', 'fraudulent', repeat('d', 64),
    '2026-08-11T12:00:00Z'
  )$$,
  'An open dispute event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('2', 64)),
  'suspended',
  'An open dispute suspends the license'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_dispute_won', 'charge.dispute.closed', 'dp_test', null,
    'pi_test_dispute', 'ch_test_dispute', null, 'dp_test',
    499900, 'inr', 'won', 'fraudulent', repeat('e', 64),
    '2026-08-11T13:00:00Z'
  )$$,
  'A won dispute event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('2', 64)),
  'active',
  'A won dispute restores the license when no other adverse state exists'
);
select lives_ok(
  $$select public.record_payment_event(
    'evt_dispute_stale_lost', 'charge.dispute.closed', 'dp_test', null,
    'pi_test_dispute', 'ch_test_dispute', null, 'dp_test',
    499900, 'inr', 'lost', 'fraudulent', repeat('f', 64),
    '2026-08-11T11:30:00Z'
  )$$,
  'An out-of-order stale dispute event is accepted'
);
select is(
  (select status from public.licenses where key_hash = repeat('2', 64)),
  'active',
  'A stale dispute event cannot override the latest resolved state'
);
select is(
  public.verify_license(
    repeat('2', 64), repeat('a', 64), 'device a', '1.0.0', 3
  )->>'valid',
  'true',
  'The first device activates'
);
select is(
  public.verify_license(
    repeat('2', 64), repeat('b', 64), 'device b', '1.0.0', 3
  )->>'valid',
  'true',
  'The second device activates'
);
select is(
  public.verify_license(
    repeat('2', 64), repeat('c', 64), 'device c', '1.0.0', 3
  )->>'valid',
  'true',
  'The third device activates'
);
select is(
  public.verify_license(
    repeat('2', 64), repeat('d', 64), 'device d', '1.0.0', 3
  )->>'code',
  'ACTIVATION_LIMIT',
  'A fourth device is rejected'
);

select * from finish();
rollback;
