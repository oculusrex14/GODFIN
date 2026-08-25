alter table public.license_activations
  add column if not exists device_label text,
  add column if not exists deactivated_at timestamptz;

create index if not exists license_activations_active_idx
  on public.license_activations(license_id)
  where deactivated_at is null;

drop function if exists public.verify_license(text, text, text);

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
set search_path = public
as $$
declare
  v_license public.licenses%rowtype;
  v_activation public.license_activations%rowtype;
  v_activation_count integer;
  v_balance bigint;
begin
  if p_activation_limit < 1 or p_activation_limit > 10 then
    raise exception 'Invalid activation limit';
  end if;

  select *
    into v_license
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

  if v_license.status <> 'active' then
    return jsonb_build_object(
      'valid', false,
      'code', 'LICENSE_' || upper(v_license.status),
      'message', 'This license is not active.'
    );
  end if;

  select *
    into v_activation
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
    )
    returning * into v_activation;
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

  select coalesce(balance, 0)
    into v_balance
  from public.credit_balances
  where user_id = v_license.user_id;

  return jsonb_build_object(
    'valid', true,
    'code', 'LICENSE_ACTIVE',
    'tier', v_license.tier,
    'activation_id', v_activation.id,
    'activation_limit', p_activation_limit,
    'topup_credits', coalesce(v_balance, 0),
    'verified_at', now()
  );
end;
$$;

revoke all on function public.verify_license(text, text, text, text, integer)
  from public, anon, authenticated;
grant execute on function public.verify_license(text, text, text, text, integer)
  to service_role;

create table if not exists public.waitlist_entries (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  email_normalized text not null unique,
  country text not null check (country ~ '^[A-Z]{2}$'),
  os text not null check (os in ('macos', 'windows', 'linux', 'other')),
  intended_use text not null check (char_length(intended_use) between 2 and 500),
  consent_version text not null,
  attribution jsonb not null default '{}'::jsonb,
  confirmation_token_hash text not null unique check (length(confirmation_token_hash) = 64),
  confirmation_expires_at timestamptz not null,
  confirmation_sent_at timestamptz,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.waitlist_entries enable row level security;

revoke all on public.waitlist_entries from public, anon, authenticated;
grant all on public.waitlist_entries to service_role;
