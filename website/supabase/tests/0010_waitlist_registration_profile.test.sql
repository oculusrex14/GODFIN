begin;
select plan(11);

select has_column('public', 'waitlist_entries', 'display_name', 'Waitlist stores a candidate name');
select has_column('public', 'waitlist_entries', 'occupation', 'Waitlist stores an optional occupation');
select has_column('public', 'waitlist_entries', 'bank_count', 'Waitlist stores an optional bank count');
select has_column('public', 'waitlist_entries', 'banks', 'Waitlist stores optional bank names');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.waitlist_entries'::regclass),
  'Waitlist row-level security remains enabled'
);
select ok(
  not has_table_privilege('anon', 'public.waitlist_entries', 'SELECT')
    and not has_table_privilege('authenticated', 'public.waitlist_entries', 'SELECT'),
  'Candidate profiles remain unavailable to browser roles'
);

select lives_ok(
  $$insert into public.waitlist_entries (
    email, email_normalized, country, os, display_name, occupation,
    bank_count, banks, intended_use, consent_version,
    confirmation_token_hash, confirmation_expires_at
  ) values (
    'candidate@example.test', 'candidate@example.test', 'IN', 'macos',
    'Test Candidate', 'Student', 2, array['HDFC Bank', 'SBI'], '',
    'waitlist-test-v2', repeat('a', 64), now() + interval '1 day'
  )$$,
  'A valid candidate profile can be stored without financial identifiers'
);
select is(
  (select array_length(banks, 1) from public.waitlist_entries where email_normalized = 'candidate@example.test'),
  2,
  'Only the supplied bank names are stored'
);

select throws_ok(
  $$update public.waitlist_entries set bank_count = 26 where email_normalized = 'candidate@example.test'$$,
  '23514',
  null,
  'Bank count is bounded'
);
select throws_ok(
  $$update public.waitlist_entries set banks = array[
    'Bank 1', 'Bank 2', 'Bank 3', 'Bank 4', 'Bank 5', 'Bank 6', 'Bank 7',
    'Bank 8', 'Bank 9', 'Bank 10', 'Bank 11', 'Bank 12', 'Bank 13'
  ] where email_normalized = 'candidate@example.test'$$,
  '23514',
  null,
  'Bank-name arrays are bounded'
);
select throws_ok(
  $$update public.waitlist_entries set intended_use = repeat('x', 1001) where email_normalized = 'candidate@example.test'$$,
  '23514',
  null,
  'Optional candidate context is bounded'
);

select * from finish();
rollback;
