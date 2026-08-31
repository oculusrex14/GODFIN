-- Additive beta-operations model. Ordinary desktop financial data remains
-- outside Supabase; these tables contain website waitlist/access metadata only.

alter table public.waitlist_entries
  alter column country drop not null,
  add column if not exists country_source text not null default 'unknown',
  add column if not exists profile_token_hash text,
  add column if not exists profile_token_expires_at timestamptz,
  add column if not exists profile_completed_at timestamptz;

alter table public.waitlist_entries
  drop constraint if exists waitlist_entries_country_source_check,
  add constraint waitlist_entries_country_source_check
    check (country_source in ('vercel_geo', 'locale', 'unknown')),
  drop constraint if exists waitlist_entries_country_check,
  add constraint waitlist_entries_country_check
    check (country is null or country ~ '^[A-Z]{2}$'),
  drop constraint if exists waitlist_entries_profile_token_hash_check,
  add constraint waitlist_entries_profile_token_hash_check
    check (profile_token_hash is null or profile_token_hash ~ '^[0-9a-f]{64}$');

create unique index if not exists waitlist_entries_profile_token_hash_idx
  on public.waitlist_entries(profile_token_hash)
  where profile_token_hash is not null;

create table if not exists public.beta_candidate_profiles (
  id uuid primary key default gen_random_uuid(),
  waitlist_entry_id uuid not null unique
    references public.waitlist_entries(id) on delete cascade,
  banks text[] not null default '{}',
  primary_use text[] not null default '{}',
  gmail_test_interest boolean not null default false,
  feedback_commitment boolean not null default false,
  platform_detail text,
  additional_context text,
  consent_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (coalesce(array_length(banks, 1), 0) <= 12),
  check (coalesce(array_length(primary_use, 1), 0) <= 12),
  check (platform_detail is null or char_length(platform_detail) <= 160),
  check (additional_context is null or char_length(additional_context) <= 1000)
);

create table if not exists public.beta_testers (
  id uuid primary key default gen_random_uuid(),
  waitlist_entry_id uuid not null unique
    references public.waitlist_entries(id) on delete restrict,
  user_id uuid unique references auth.users(id) on delete set null,
  email_normalized text not null unique,
  cohort text not null,
  status text not null default 'shortlisted',
  phase text not null default 'core',
  gmail_test_user_required boolean not null default false,
  gmail_test_user_added_at timestamptz,
  checkout_test_eligible boolean not null default false,
  checkout_test_completed_at timestamptz,
  feedback_quality text not null default 'unrated',
  owner_notes text,
  invited_at timestamptz,
  accepted_at timestamptz,
  paused_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (email_normalized = lower(email_normalized)),
  check (email_normalized ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
  check (cohort ~ '^[a-z0-9][a-z0-9_-]{1,39}$'),
  check (status in (
    'shortlisted', 'invited', 'accepted', 'active', 'paused',
    'completed', 'declined', 'revoked'
  )),
  check (phase in ('core', 'pro', 'max', 'checkout_test')),
  check (feedback_quality in ('unrated', 'low', 'useful', 'high_signal')),
  check (owner_notes is null or char_length(owner_notes) <= 2000)
);

create index if not exists beta_testers_status_phase_idx
  on public.beta_testers(status, phase, created_at desc);

create table if not exists public.beta_invites (
  id uuid primary key default gen_random_uuid(),
  beta_tester_id uuid not null references public.beta_testers(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  sent_at timestamptz,
  used_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
);

create unique index if not exists beta_invites_one_live_per_tester_idx
  on public.beta_invites(beta_tester_id)
  where used_at is null and revoked_at is null;

create table if not exists public.beta_feedback (
  id uuid primary key default gen_random_uuid(),
  beta_tester_id uuid not null references public.beta_testers(id) on delete restrict,
  user_id uuid not null references auth.users(id) on delete restrict,
  category text not null,
  feature_screen text not null,
  happened text not null,
  expected text not null,
  reproduction_steps text,
  severity text not null,
  may_contact boolean not null default false,
  app_version text,
  platform text,
  status text not null default 'new',
  feedback_quality text not null default 'unrated',
  owner_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (category in ('bug', 'ux', 'parser', 'performance', 'feature', 'other')),
  check (char_length(feature_screen) between 2 and 100),
  check (char_length(happened) between 10 and 2000),
  check (char_length(expected) between 10 and 2000),
  check (reproduction_steps is null or char_length(reproduction_steps) <= 3000),
  check (severity in ('low', 'medium', 'high', 'blocking')),
  check (app_version is null or char_length(app_version) <= 64),
  check (platform is null or char_length(platform) <= 100),
  check (status in ('new', 'reviewing', 'resolved', 'closed')),
  check (feedback_quality in ('unrated', 'low', 'useful', 'high_signal')),
  check (owner_note is null or char_length(owner_note) <= 2000)
);

create index if not exists beta_feedback_tester_created_idx
  on public.beta_feedback(beta_tester_id, created_at desc);

create table if not exists public.beta_checkout_attempts (
  id uuid primary key default gen_random_uuid(),
  beta_tester_id uuid not null references public.beta_testers(id) on delete restrict,
  user_id uuid not null references auth.users(id) on delete restrict,
  provider text not null default 'cashfree',
  provider_order_id text not null unique,
  provider_order_reference_id text,
  provider_payment_id text,
  amount_total bigint not null default 100 check (amount_total = 100),
  currency text not null default 'inr' check (currency = 'inr'),
  status text not null default 'created',
  idempotency_key text not null unique,
  event_payload_sha256 text,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (provider = 'cashfree'),
  check (provider_order_id ~ '^godfin_beta_[0-9a-f-]{36}$'),
  check (status in (
    'created', 'paid', 'failed', 'abandoned', 'refund_pending',
    'refunded', 'disputed', 'dispute_lost', 'review'
  )),
  check (event_payload_sha256 is null or event_payload_sha256 ~ '^[0-9a-f]{64}$')
);

create index if not exists beta_checkout_tester_created_idx
  on public.beta_checkout_attempts(beta_tester_id, created_at desc);

create table if not exists public.beta_events (
  id bigint generated always as identity primary key,
  beta_tester_id uuid references public.beta_testers(id) on delete set null,
  event_type text not null,
  actor text not null,
  reason text,
  metadata jsonb not null default '{}'::jsonb,
  event_key text unique,
  created_at timestamptz not null default now(),
  check (event_type ~ '^[a-z0-9:_-]{2,80}$'),
  check (char_length(actor) between 2 and 160),
  check (reason is null or char_length(reason) <= 1000),
  check (event_key is null or char_length(event_key) between 16 and 220)
);

create index if not exists beta_events_tester_created_idx
  on public.beta_events(beta_tester_id, created_at desc);

alter table public.licenses
  add column if not exists beta_tester_id uuid
    references public.beta_testers(id) on delete set null,
  add column if not exists expires_at timestamptz;

alter table public.licenses
  drop constraint if exists licenses_kind_check,
  add constraint licenses_kind_check
    check (kind in ('purchase', 'owner_test', 'beta_test')),
  drop constraint if exists licenses_beta_shape_check,
  add constraint licenses_beta_shape_check check (
    (kind = 'beta_test' and beta_tester_id is not null and expires_at is not null)
    or
    (kind <> 'beta_test' and beta_tester_id is null)
  );

create unique index if not exists licenses_one_beta_per_tester_idx
  on public.licenses(beta_tester_id)
  where kind = 'beta_test';

comment on column public.licenses.kind is
  'purchase is paid access, owner_test is non-revenue owner testing, and beta_test is revocable pre-release tester access.';

alter table public.beta_candidate_profiles enable row level security;
alter table public.beta_testers enable row level security;
alter table public.beta_invites enable row level security;
alter table public.beta_feedback enable row level security;
alter table public.beta_checkout_attempts enable row level security;
alter table public.beta_events enable row level security;

revoke all on table
  public.beta_candidate_profiles,
  public.beta_testers,
  public.beta_invites,
  public.beta_feedback,
  public.beta_checkout_attempts,
  public.beta_events
from public, anon, authenticated;

grant all on table
  public.beta_candidate_profiles,
  public.beta_testers,
  public.beta_invites,
  public.beta_feedback,
  public.beta_checkout_attempts,
  public.beta_events
to service_role;

grant usage, select on sequence public.beta_events_id_seq to service_role;

create or replace function public.accept_beta_invite(
  p_token_hash text,
  p_user_id uuid,
  p_email text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_invite public.beta_invites%rowtype;
  v_tester public.beta_testers%rowtype;
  v_email text := lower(trim(coalesce(p_email, '')));
begin
  if coalesce(p_token_hash, '') !~ '^[0-9a-f]{64}$'
    or p_user_id is null
    or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
    return jsonb_build_object('accepted', false, 'code', 'INVITE_INVALID');
  end if;

  select * into v_invite
  from public.beta_invites
  where token_hash = p_token_hash
  for update;

  if v_invite.id is null
    or v_invite.used_at is not null
    or v_invite.revoked_at is not null
    or v_invite.expires_at <= now() then
    return jsonb_build_object('accepted', false, 'code', 'INVITE_INVALID');
  end if;

  select * into v_tester
  from public.beta_testers
  where id = v_invite.beta_tester_id
  for update;

  if v_tester.id is null
    or v_tester.status not in ('invited', 'accepted')
    or v_tester.email_normalized <> v_email
    or (v_tester.user_id is not null and v_tester.user_id <> p_user_id)
    or exists (
      select 1 from public.beta_testers other
      where other.user_id = p_user_id and other.id <> v_tester.id
    ) then
    return jsonb_build_object('accepted', false, 'code', 'INVITE_INVALID');
  end if;

  update public.beta_invites
  set used_at = now()
  where id = v_invite.id;

  update public.beta_testers
  set user_id = p_user_id,
      status = 'active',
      phase = 'core',
      accepted_at = coalesce(accepted_at, now()),
      updated_at = now()
  where id = v_tester.id
  returning * into v_tester;

  insert into public.beta_events (
    beta_tester_id, event_type, actor, reason
  ) values (
    v_tester.id, 'invite:accepted', 'website:' || p_user_id::text,
    'Google identity matched the invited email.'
  );

  return jsonb_build_object(
    'accepted', true,
    'code', 'INVITE_ACCEPTED',
    'tester_id', v_tester.id,
    'phase', v_tester.phase,
    'status', v_tester.status
  );
end;
$$;

revoke all on function public.accept_beta_invite(text, uuid, text)
  from public, anon, authenticated;
grant execute on function public.accept_beta_invite(text, uuid, text)
  to service_role;

create or replace function public.set_beta_tester_access(
  p_tester_id uuid,
  p_phase text,
  p_status text,
  p_license_hash text,
  p_license_last4 text,
  p_expires_at timestamptz,
  p_actor text,
  p_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_tester public.beta_testers%rowtype;
  v_license public.licenses%rowtype;
  v_license_status text;
begin
  if p_phase not in ('core', 'pro', 'max')
    or p_status not in ('active', 'paused', 'completed', 'revoked')
    or char_length(trim(coalesce(p_actor, ''))) < 2 then
    raise exception 'Invalid beta access transition';
  end if;

  select * into v_tester
  from public.beta_testers
  where id = p_tester_id
  for update;

  if v_tester.id is null or v_tester.user_id is null then
    raise exception 'Beta tester is not identity-bound';
  end if;

  select * into v_license
  from public.licenses
  where beta_tester_id = v_tester.id
  for update;

  v_license_status := case when p_status = 'active' then 'active' else 'revoked' end;

  if p_phase in ('pro', 'max') then
    if coalesce(p_license_hash, '') !~ '^[0-9a-f]{64}$'
      or coalesce(p_license_last4, '') !~ '^[A-Za-z0-9]{4}$'
      or p_expires_at is null
      or p_expires_at <= now() then
      raise exception 'Valid beta license material and expiry are required';
    end if;

    if v_license.id is null then
      insert into public.licenses (
        user_id, tier, key_hash, key_last4, kind, status,
        state_version, beta_tester_id, expires_at
      ) values (
        v_tester.user_id, p_phase, p_license_hash, p_license_last4,
        'beta_test', v_license_status, 1, v_tester.id, p_expires_at
      ) returning * into v_license;
    else
      update public.licenses
      set tier = p_phase,
          status = v_license_status,
          expires_at = p_expires_at,
          state_version = case
            when tier is distinct from p_phase
              or status is distinct from v_license_status
              or expires_at is distinct from p_expires_at
            then state_version + 1 else state_version end
      where id = v_license.id
      returning * into v_license;
    end if;
  elsif v_license.id is not null then
    update public.licenses
    set status = 'revoked',
        state_version = case when status <> 'revoked' then state_version + 1 else state_version end
    where id = v_license.id
    returning * into v_license;
  end if;

  update public.beta_testers
  set phase = p_phase,
      status = p_status,
      paused_at = case when p_status = 'paused' then now() else paused_at end,
      completed_at = case when p_status = 'completed' then now() else completed_at end,
      updated_at = now()
  where id = v_tester.id
  returning * into v_tester;

  insert into public.beta_events (
    beta_tester_id, event_type, actor, reason,
    metadata
  ) values (
    v_tester.id,
    'access:' || p_status,
    left(trim(p_actor), 160),
    left(p_reason, 1000),
    jsonb_build_object('phase', p_phase, 'license_id', v_license.id)
  );

  return jsonb_build_object(
    'tester_id', v_tester.id,
    'phase', v_tester.phase,
    'status', v_tester.status,
    'license_id', v_license.id,
    'license_status', v_license.status,
    'license_state_version', v_license.state_version
  );
end;
$$;

revoke all on function public.set_beta_tester_access(
  uuid, text, text, text, text, timestamptz, text, text
) from public, anon, authenticated;
grant execute on function public.set_beta_tester_access(
  uuid, text, text, text, text, timestamptz, text, text
) to service_role;

drop function if exists public.verify_license(text, text, text, text, integer);
create or replace function public.verify_license(
  p_license_hash text,
  p_machine_hash text,
  p_device_label text,
  p_app_version text,
  p_activation_limit integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_license public.licenses%rowtype;
  v_activation public.license_activations%rowtype;
  v_activation_count integer;
begin
  if p_activation_limit is null
    or p_activation_limit < 1
    or p_activation_limit > 3 then
    raise exception 'Invalid activation limit';
  end if;
  if coalesce(p_license_hash, '') !~ '^[0-9a-f]{64}$'
    or coalesce(p_machine_hash, '') !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object(
      'valid', false,
      'code', 'INVALID_REQUEST',
      'message', 'License key or device ID is invalid.'
    );
  end if;

  select * into v_license
  from public.licenses
  where key_hash = p_license_hash
  for update;

  if v_license.id is null then
    return jsonb_build_object(
      'valid', false,
      'code', 'LICENSE_NOT_FOUND',
      'message', 'License key was not recognized.'
    );
  end if;
  if v_license.kind = 'beta_test'
    and (v_license.expires_at is null or v_license.expires_at <= now()) then
    update public.licenses
    set status = 'revoked',
        state_version = case when status <> 'revoked' then state_version + 1 else state_version end
    where id = v_license.id
    returning * into v_license;
    return jsonb_build_object(
      'valid', false,
      'code', 'LICENSE_EXPIRED',
      'message', 'This beta license has expired.'
    );
  end if;
  if v_license.status <> 'active' then
    return jsonb_build_object(
      'valid', false,
      'code', 'LICENSE_' || upper(v_license.status),
      'message', 'This license is not active.'
    );
  end if;

  select * into v_activation
  from public.license_activations
  where license_id = v_license.id
    and machine_hash = p_machine_hash
  for update;

  if v_activation.id is null or v_activation.deactivated_at is not null then
    select count(*) into v_activation_count
    from public.license_activations
    where license_id = v_license.id
      and deactivated_at is null;
    if v_activation_count >= p_activation_limit then
      return jsonb_build_object(
        'valid', false,
        'code', 'ACTIVATION_LIMIT',
        'message', 'This license has reached its three-device limit.'
      );
    end if;
  end if;

  if v_activation.id is null then
    insert into public.license_activations (
      license_id, machine_hash, device_label, app_version
    ) values (
      v_license.id,
      p_machine_hash,
      left(coalesce(p_device_label, 'GODFIN device'), 80),
      left(p_app_version, 32)
    ) returning * into v_activation;
  else
    update public.license_activations
    set last_seen_at = now(),
        device_label = left(coalesce(p_device_label, device_label, 'GODFIN device'), 80),
        app_version = coalesce(left(p_app_version, 32), app_version),
        deactivated_at = null
    where id = v_activation.id
    returning * into v_activation;
  end if;

  update public.licenses
  set last_verified_at = now()
  where id = v_license.id;

  return jsonb_build_object(
    'valid', true,
    'code', 'LICENSE_ACTIVE',
    'license_id', v_license.id,
    'license_state_version', v_license.state_version,
    'tier', v_license.tier,
    'license_kind', v_license.kind,
    'license_expires_at', v_license.expires_at,
    'activation_id', v_activation.id,
    'activation_limit', p_activation_limit,
    'topup_credits', 0,
    'verified_at', now()
  );
end;
$$;

revoke all on function public.verify_license(text, text, text, text, integer)
  from public, anon, authenticated;
grant execute on function public.verify_license(text, text, text, text, integer)
  to service_role;

alter function public.accept_beta_invite(text, uuid, text) set search_path = '';
alter function public.set_beta_tester_access(
  uuid, text, text, text, text, timestamptz, text, text
) set search_path = '';
alter function public.verify_license(text, text, text, text, integer)
  set search_path = '';
