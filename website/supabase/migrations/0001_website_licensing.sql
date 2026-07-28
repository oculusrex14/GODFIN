create extension if not exists pgcrypto;

create table if not exists public.licenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  tier text not null check (tier in ('pro', 'max')),
  key_hash text not null unique check (length(key_hash) = 64),
  key_last4 text not null check (length(key_last4) = 4),
  status text not null default 'active' check (status in ('active', 'suspended', 'revoked')),
  issued_at timestamptz not null default now(),
  last_verified_at timestamptz
);

create index if not exists licenses_user_id_idx on public.licenses(user_id);

create table if not exists public.purchases (
  id uuid primary key default gen_random_uuid(),
  checkout_session_id text not null unique,
  user_id uuid not null references auth.users(id) on delete cascade,
  product_code text not null,
  amount_total bigint not null check (amount_total >= 0),
  currency text not null,
  status text not null default 'paid',
  license_id uuid references public.licenses(id) on delete set null,
  credits bigint not null default 0 check (credits >= 0),
  email_sent_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists purchases_user_id_idx on public.purchases(user_id);

create table if not exists public.credit_balances (
  user_id uuid primary key references auth.users(id) on delete cascade,
  balance bigint not null default 0 check (balance >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.license_activations (
  id uuid primary key default gen_random_uuid(),
  license_id uuid not null references public.licenses(id) on delete cascade,
  machine_hash text not null check (length(machine_hash) = 64),
  app_version text,
  activated_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (license_id, machine_hash)
);

create index if not exists license_activations_license_id_idx
  on public.license_activations(license_id);

alter table public.licenses enable row level security;
alter table public.purchases enable row level security;
alter table public.credit_balances enable row level security;
alter table public.license_activations enable row level security;

create policy "Users read their own licenses"
  on public.licenses for select
  using (auth.uid() = user_id);

create policy "Users read their own purchases"
  on public.purchases for select
  using (auth.uid() = user_id);

create policy "Users read their own credit balance"
  on public.credit_balances for select
  using (auth.uid() = user_id);

create policy "Users read activations for their licenses"
  on public.license_activations for select
  using (
    exists (
      select 1 from public.licenses
      where licenses.id = license_activations.license_id
        and licenses.user_id = auth.uid()
    )
  );

create or replace function public.provision_purchase(
  p_checkout_session_id text,
  p_user_id uuid,
  p_product_code text,
  p_amount_total bigint,
  p_currency text,
  p_license_tier text,
  p_license_hash text,
  p_license_last4 text,
  p_credits bigint
)
returns table (
  purchase_id uuid,
  license_id uuid,
  created boolean,
  email_sent_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_purchase_id uuid;
  v_license_id uuid;
  v_email_sent_at timestamptz;
begin
  perform pg_advisory_xact_lock(hashtext(p_checkout_session_id));

  select p.id, p.license_id, p.email_sent_at
    into v_purchase_id, v_license_id, v_email_sent_at
  from public.purchases p
  where p.checkout_session_id = $1;

  if v_purchase_id is not null then
    return query select v_purchase_id, v_license_id, false, v_email_sent_at;
    return;
  end if;

  if p_license_tier is not null then
    if p_license_tier not in ('pro', 'max')
      or p_license_hash is null
      or p_license_last4 is null then
      raise exception 'Invalid license provisioning input';
    end if;

    insert into public.licenses (
      user_id, tier, key_hash, key_last4
    ) values (
      p_user_id, p_license_tier, p_license_hash, p_license_last4
    )
    returning id into v_license_id;
  end if;

  if p_credits > 0 then
    insert into public.credit_balances (user_id, balance)
    values (p_user_id, p_credits)
    on conflict (user_id) do update
      set balance = public.credit_balances.balance + excluded.balance,
          updated_at = now();
  end if;

  insert into public.purchases (
    checkout_session_id,
    user_id,
    product_code,
    amount_total,
    currency,
    license_id,
    credits
  ) values (
    p_checkout_session_id,
    p_user_id,
    p_product_code,
    p_amount_total,
    lower(p_currency),
    v_license_id,
    p_credits
  )
  returning id into v_purchase_id;

  return query select v_purchase_id, v_license_id, true, null::timestamptz;
end;
$$;

create or replace function public.verify_license(
  p_license_hash text,
  p_machine_hash text,
  p_app_version text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_license public.licenses%rowtype;
  v_activation_count integer;
  v_activation_limit integer;
  v_balance bigint;
  v_monthly_credits integer;
  v_features jsonb;
begin
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

  update public.license_activations
  set last_seen_at = now(),
      app_version = coalesce(p_app_version, app_version)
  where license_id = v_license.id
    and machine_hash = p_machine_hash;

  if not found then
    select count(*) into v_activation_count
    from public.license_activations
    where license_id = v_license.id;

    v_activation_limit := case when v_license.tier = 'max' then 5 else 2 end;
    if v_activation_count >= v_activation_limit then
      return jsonb_build_object(
        'valid', false,
        'code', 'ACTIVATION_LIMIT',
        'message', 'This license has reached its device limit.'
      );
    end if;

    insert into public.license_activations (
      license_id, machine_hash, app_version
    ) values (
      v_license.id, p_machine_hash, p_app_version
    );
  end if;

  update public.licenses
  set last_verified_at = now()
  where id = v_license.id;

  select coalesce(balance, 0)
    into v_balance
  from public.credit_balances
  where user_id = v_license.user_id;
  v_balance := coalesce(v_balance, 0);

  if v_license.tier = 'max' then
    v_monthly_credits := 2500;
    v_features := '[
      "multi_bank", "ai_classification", "advanced_reports",
      "encrypted_backup", "multi_device_sync", "family_profiles",
      "white_label_reports", "local_api", "early_access"
    ]'::jsonb;
  else
    v_monthly_credits := 500;
    v_features := '[
      "multi_bank", "ai_classification", "advanced_reports",
      "encrypted_backup", "multi_device_sync"
    ]'::jsonb;
  end if;

  return jsonb_build_object(
    'valid', true,
    'code', 'LICENSE_ACTIVE',
    'tier', v_license.tier,
    'features', v_features,
    'monthly_credits', v_monthly_credits,
    'topup_credits', v_balance,
    'verified_at', now()
  );
end;
$$;

revoke all on function public.provision_purchase(
  text, uuid, text, bigint, text, text, text, text, bigint
) from public, anon, authenticated;
grant execute on function public.provision_purchase(
  text, uuid, text, bigint, text, text, text, text, bigint
) to service_role;

revoke all on function public.verify_license(text, text, text)
  from public, anon, authenticated;
grant execute on function public.verify_license(text, text, text)
  to service_role;
