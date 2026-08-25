begin;
select plan(13);

select ok(
  has_function_privilege(
    'service_role',
    'public.check_public_rate_limit(text,text,integer,integer)',
    'EXECUTE'
  ),
  'service_role can apply public rate limits'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.check_public_rate_limit(text,text,integer,integer)',
    'EXECUTE'
  ),
  'anon cannot call the rate-limit function'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.check_public_rate_limit(text,text,integer,integer)',
    'EXECUTE'
  ),
  'authenticated users cannot call the rate-limit function'
);
select is(
  (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = 'public.public_rate_limits'::regclass
  ),
  true,
  'The rate-limit table has RLS enabled'
);
select ok(
  not has_table_privilege('anon', 'public.public_rate_limits', 'SELECT'),
  'anon cannot read hashed rate-limit subjects'
);

select is(
  (
    public.check_public_rate_limit(
      'test:address', repeat('a', 64), 2, 3600
    )->>'allowed'
  )::boolean,
  true,
  'The first request is allowed'
);
select is(
  (
    public.check_public_rate_limit(
      'test:address', repeat('a', 64), 2, 3600
    )->>'allowed'
  )::boolean,
  true,
  'The second request is allowed'
);
select is(
  (
    public.check_public_rate_limit(
      'test:address', repeat('a', 64), 2, 3600
    )->>'allowed'
  )::boolean,
  false,
  'A request above the limit is blocked'
);
select ok(
  (
    public.check_public_rate_limit(
      'test:address', repeat('a', 64), 2, 3600
    )->>'retry_after'
  )::integer > 0,
  'A blocked request receives a positive retry interval'
);
select is(
  (
    public.check_public_rate_limit(
      'test:address', repeat('b', 64), 2, 3600
    )->>'allowed'
  )::boolean,
  true,
  'A distinct hashed subject has an independent limit'
);
select is(
  (
    public.check_public_rate_limit(
      'test:email', repeat('a', 64), 2, 3600
    )->>'allowed'
  )::boolean,
  true,
  'A distinct bucket has an independent limit'
);
select is(
  (
    select request_count
    from public.public_rate_limits
    where bucket = 'test:address' and subject_hash = repeat('a', 64)
  ),
  4::bigint,
  'Attempts are counted atomically, including blocked attempts'
);

update public.public_rate_limits
set window_start = now() - interval '2 hours',
    expires_at = now() - interval '1 hour'
where bucket = 'test:address' and subject_hash = repeat('a', 64);
select is(
  (
    public.check_public_rate_limit(
      'test:address', repeat('a', 64), 2, 3600
    )->>'remaining'
  )::integer,
  1,
  'An expired window resets atomically'
);

select * from finish();
rollback;
