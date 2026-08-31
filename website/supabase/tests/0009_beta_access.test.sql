begin;
select plan(39);

select has_table('public', 'beta_candidate_profiles', 'Candidate profiles exist');
select has_table('public', 'beta_testers', 'Beta testers exist');
select has_table('public', 'beta_invites', 'Hashed beta invites exist');
select has_table('public', 'beta_feedback', 'Beta feedback exists');
select has_table('public', 'beta_checkout_attempts', 'Isolated beta checkout ledger exists');
select has_table('public', 'beta_events', 'Beta audit events exist');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.beta_testers'::regclass),
  'Beta tester RLS is enabled'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.beta_feedback'::regclass),
  'Beta feedback RLS is enabled'
);
select ok(
  not has_table_privilege('anon', 'public.beta_testers', 'SELECT')
    and not has_table_privilege('authenticated', 'public.beta_testers', 'SELECT'),
  'Operational tester rows are not client-readable'
);
select ok(
  not has_table_privilege('anon', 'public.beta_invites', 'SELECT')
    and not has_table_privilege('authenticated', 'public.beta_invites', 'SELECT'),
  'Invite hashes are service-role only'
);
select ok(
  not has_table_privilege('authenticated', 'public.beta_feedback', 'UPDATE'),
  'Authenticated clients cannot alter owner feedback metadata'
);
select ok(
  has_function_privilege(
    'service_role', 'public.accept_beta_invite(text,uuid,text)', 'EXECUTE'
  )
    and not has_function_privilege(
      'authenticated', 'public.accept_beta_invite(text,uuid,text)', 'EXECUTE'
    ),
  'Invite acceptance is a server-only operation'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.set_beta_tester_access(uuid,text,text,text,text,timestamp with time zone,text,text)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'authenticated',
      'public.set_beta_tester_access(uuid,text,text,text,text,timestamp with time zone,text,text)',
      'EXECUTE'
    ),
  'Beta promotion is a server-only operation'
);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values
  (
    '00000000-0000-0000-0000-000000000000',
    '91111111-1111-4111-8111-111111111111',
    'authenticated', 'authenticated', 'beta-one@example.test', '',
    now(), now(), now(), '{}'::jsonb, '{}'::jsonb
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '92222222-2222-4222-8222-222222222222',
    'authenticated', 'authenticated', 'other@example.test', '',
    now(), now(), now(), '{}'::jsonb, '{}'::jsonb
  );

insert into public.waitlist_entries (
  id, email, email_normalized, country, country_source, os, intended_use,
  consent_version, confirmation_token_hash, confirmation_expires_at,
  confirmed_at
) values (
  '93333333-3333-4333-8333-333333333333',
  'beta-one@example.test', 'beta-one@example.test', null, 'unknown', 'macos',
  'Understand a made-up household demo', 'waitlist-test-v1', repeat('a', 64),
  now() + interval '1 day', now()
);

insert into public.beta_testers (
  id, waitlist_entry_id, email_normalized, cohort, status, phase, invited_at
) values (
  '94444444-4444-4444-8444-444444444444',
  '93333333-3333-4333-8333-333333333333',
  'beta-one@example.test', 'test-a', 'invited', 'core', now()
);

insert into public.beta_invites (
  beta_tester_id, token_hash, expires_at, sent_at
) values (
  '94444444-4444-4444-8444-444444444444', repeat('b', 64),
  now() + interval '1 day', now()
);

select is(
  public.accept_beta_invite(
    repeat('b', 64),
    '92222222-2222-4222-8222-222222222222',
    'other@example.test'
  )->>'code',
  'INVITE_INVALID',
  'A different Google email cannot bind the invite'
);
select is(
  (select used_at from public.beta_invites where token_hash = repeat('b', 64)),
  null::timestamptz,
  'A wrong-account attempt does not consume the invite'
);
select is(
  public.accept_beta_invite(
    repeat('b', 64),
    '91111111-1111-4111-8111-111111111111',
    'beta-one@example.test'
  )->>'code',
  'INVITE_ACCEPTED',
  'The matching verified identity accepts the invite'
);
select is(
  (select status from public.beta_testers where id = '94444444-4444-4444-8444-444444444444'),
  'active',
  'Accepted testers become active Core testers'
);
select is(
  (select phase from public.beta_testers where id = '94444444-4444-4444-8444-444444444444'),
  'core',
  'Core access does not fabricate a paid tier'
);
select is(
  (select count(*) from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  0::bigint,
  'Core beta access has no license'
);
select is(
  public.accept_beta_invite(
    repeat('b', 64),
    '91111111-1111-4111-8111-111111111111',
    'beta-one@example.test'
  )->>'code',
  'INVITE_INVALID',
  'An invite cannot be reused'
);

select lives_ok(
  $$select public.set_beta_tester_access(
    '94444444-4444-4444-8444-444444444444', 'pro', 'active',
    repeat('c', 64), 'BETA', now() + interval '30 days',
    'owner:test', 'Promote to Pro for the test cohort.'
  )$$,
  'The owner can provision a revocable Pro beta license'
);
select is(
  (select kind from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  'beta_test',
  'The entitlement is explicitly beta-only'
);
select is(
  (select count(*) from public.purchases),
  0::bigint,
  'Beta promotion never creates a commercial purchase'
);
select lives_ok(
  $$select public.set_beta_tester_access(
    '94444444-4444-4444-8444-444444444444', 'max', 'active',
    repeat('c', 64), 'BETA', now() + interval '30 days',
    'owner:test', 'Promote the same license to Max.'
  )$$,
  'Pro to Max updates the existing beta license'
);
select is(
  (select count(*) from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  1::bigint,
  'Promotion does not create a second license'
);
select is(
  (select tier from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  'max',
  'The same beta license becomes Max'
);
select is(
  (select state_version from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  2::bigint,
  'The signed-entitlement state version advances on promotion'
);
select is(
  public.verify_license(
    repeat('c', 64), repeat('1', 64), 'Beta device one', '1.0.0', 3
  )->>'valid',
  'true',
  'The first beta device activates'
);
select is(
  public.verify_license(
    repeat('c', 64), repeat('2', 64), 'Beta device two', '1.0.0', 3
  )->>'valid',
  'true',
  'The second beta device activates'
);
select is(
  public.verify_license(
    repeat('c', 64), repeat('3', 64), 'Beta device three', '1.0.0', 3
  )->>'valid',
  'true',
  'The third beta device activates'
);
select is(
  public.verify_license(
    repeat('c', 64), repeat('4', 64), 'Beta device four', '1.0.0', 3
  )->>'code',
  'ACTIVATION_LIMIT',
  'A fourth beta device is rejected by the normal license cap'
);

update public.licenses
set expires_at = now() - interval '1 second'
where beta_tester_id = '94444444-4444-4444-8444-444444444444';

select is(
  public.verify_license(repeat('c', 64), repeat('d', 64), 'Beta Mac', '1.0.0', 3)->>'code',
  'LICENSE_EXPIRED',
  'Expired beta licenses cannot mint a signed entitlement response'
);
select is(
  (select status from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  'revoked',
  'Expiry revokes the beta license state'
);
select is(
  (select state_version from public.licenses where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  3::bigint,
  'Expiry advances the beta license state version'
);
select is(
  (select count(*) from public.beta_events where beta_tester_id = '94444444-4444-4444-8444-444444444444'),
  3::bigint,
  'Invite acceptance and both promotions are audited'
);

select throws_ok(
  $$insert into public.beta_checkout_attempts (
    beta_tester_id, user_id, provider_order_id, amount_total, currency,
    idempotency_key
  ) values (
    '94444444-4444-4444-8444-444444444444',
    '91111111-1111-4111-8111-111111111111',
    'godfin_beta_95555555-5555-4555-8555-555555555555',
    499900, 'inr', 'wrong-amount'
  )$$,
  '23514',
  null,
  'The beta checkout ledger rejects any amount except INR 1'
);
select lives_ok(
  $$insert into public.beta_checkout_attempts (
    beta_tester_id, user_id, provider_order_id, amount_total, currency,
    idempotency_key
  ) values (
    '94444444-4444-4444-8444-444444444444',
    '91111111-1111-4111-8111-111111111111',
    'godfin_beta_96666666-6666-4666-8666-666666666666',
    100, 'inr', 'exact-inr-one'
  )$$,
  'The beta checkout ledger accepts exactly INR 1'
);
select is(
  (select amount_total from public.beta_checkout_attempts where idempotency_key = 'exact-inr-one'),
  100::bigint,
  'The stored amount is one hundred minor units'
);
select is(
  (select count(*) from public.purchases),
  0::bigint,
  'Beta checkout remains isolated from the purchase ledger'
);

select * from finish();
rollback;
