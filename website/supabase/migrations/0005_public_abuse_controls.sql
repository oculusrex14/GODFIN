create table if not exists public.public_rate_limits (
  bucket text not null check (bucket ~ '^[a-z0-9:_-]{2,80}$'),
  subject_hash text not null check (subject_hash ~ '^[0-9a-f]{64}$'),
  window_start timestamptz not null,
  request_count bigint not null check (request_count >= 1),
  expires_at timestamptz not null,
  updated_at timestamptz not null default now(),
  primary key (bucket, subject_hash)
);

create index if not exists public_rate_limits_expires_at_idx
  on public.public_rate_limits(expires_at);

alter table public.public_rate_limits enable row level security;
revoke all on public.public_rate_limits from public, anon, authenticated;
grant all on public.public_rate_limits to service_role;

create or replace function public.check_public_rate_limit(
  p_bucket text,
  p_subject_hash text,
  p_limit integer,
  p_window_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_window_start timestamptz;
  v_count bigint;
  v_expires_at timestamptz;
begin
  if coalesce(p_bucket, '') !~ '^[a-z0-9:_-]{2,80}$'
    or coalesce(p_subject_hash, '') !~ '^[0-9a-f]{64}$'
    or p_limit is null
    or p_limit < 1
    or p_limit > 10000
    or p_window_seconds is null
    or p_window_seconds < 1
    or p_window_seconds > 604800 then
    raise exception 'Invalid rate-limit input';
  end if;

  v_window_start := pg_catalog.to_timestamp(
    pg_catalog.floor(
      pg_catalog.date_part('epoch', v_now) / p_window_seconds
    ) * p_window_seconds
  );

  insert into public.public_rate_limits as current_limit (
    bucket,
    subject_hash,
    window_start,
    request_count,
    expires_at,
    updated_at
  ) values (
    p_bucket,
    p_subject_hash,
    v_window_start,
    1,
    v_window_start + pg_catalog.make_interval(secs => p_window_seconds),
    v_now
  )
  on conflict (bucket, subject_hash) do update
  set window_start = case
        when current_limit.window_start < excluded.window_start
          then excluded.window_start
        else current_limit.window_start
      end,
      request_count = case
        when current_limit.window_start < excluded.window_start then 1
        else current_limit.request_count + 1
      end,
      expires_at = case
        when current_limit.window_start < excluded.window_start
          then excluded.expires_at
        else current_limit.expires_at
      end,
      updated_at = v_now
  returning request_count, expires_at
  into v_count, v_expires_at;

  delete from public.public_rate_limits
  where ctid in (
    select ctid
    from public.public_rate_limits
    where expires_at < v_now - pg_catalog.make_interval(days => 7)
    order by expires_at
    limit 100
  );

  return pg_catalog.jsonb_build_object(
    'allowed', v_count <= p_limit,
    'limit', p_limit,
    'remaining', pg_catalog.greatest(0, p_limit - v_count),
    'retry_after', pg_catalog.greatest(
      1,
      pg_catalog.ceil(
        pg_catalog.date_part('epoch', v_expires_at - v_now)
      )::integer
    )
  );
end;
$$;

revoke all on function public.check_public_rate_limit(
  text, text, integer, integer
) from public, anon, authenticated;
grant execute on function public.check_public_rate_limit(
  text, text, integer, integer
) to service_role;

alter function public.check_public_rate_limit(
  text, text, integer, integer
) set search_path = '';
