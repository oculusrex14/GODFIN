create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

alter default privileges in schema public revoke execute on functions from public;
alter default privileges in schema public revoke execute on functions from anon, authenticated;

alter table public.licenses
  add column if not exists state_version bigint not null default 1
    check (state_version >= 1);

alter table public.purchases
  add column if not exists payment_intent_id text,
  add column if not exists charge_id text,
  add column if not exists stripe_customer_id text,
  add column if not exists billing_country text,
  add column if not exists pricing_country text,
  add column if not exists pricing_version text,
  add column if not exists pricing_review_reason text,
  add column if not exists refunded_amount bigint not null default 0
    check (refunded_amount >= 0),
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists purchases_payment_intent_id_uidx
  on public.purchases(payment_intent_id)
  where payment_intent_id is not null;
create index if not exists purchases_charge_id_idx
  on public.purchases(charge_id)
  where charge_id is not null;

create table if not exists public.payment_events (
  id uuid primary key default gen_random_uuid(),
  stripe_event_id text not null unique,
  event_type text not null,
  object_id text,
  checkout_session_id text,
  payment_intent_id text,
  charge_id text,
  refund_id text,
  dispute_id text,
  purchase_id uuid references public.purchases(id) on delete set null,
  amount bigint check (amount is null or amount >= 0),
  currency text,
  event_status text,
  reason text,
  payload_sha256 text not null check (length(payload_sha256) = 64),
  occurred_at timestamptz not null,
  mapped_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists payment_events_purchase_id_idx
  on public.payment_events(purchase_id);
create index if not exists payment_events_payment_intent_id_idx
  on public.payment_events(payment_intent_id)
  where payment_intent_id is not null;
create index if not exists payment_events_charge_id_idx
  on public.payment_events(charge_id)
  where charge_id is not null;

create table if not exists public.license_status_history (
  id uuid primary key default gen_random_uuid(),
  license_id uuid not null references public.licenses(id) on delete cascade,
  previous_status text,
  new_status text not null check (new_status in ('active', 'suspended', 'revoked')),
  state_version bigint not null check (state_version >= 1),
  source_event_id text,
  reason text not null,
  created_at timestamptz not null default now()
);

create index if not exists license_status_history_license_id_idx
  on public.license_status_history(license_id, created_at desc);

create table if not exists public.godfin_migration_evidence (
  version text primary key,
  expected_sha256 text not null check (length(expected_sha256) = 64),
  deployed_at timestamptz not null default now(),
  deployed_by text not null,
  environment text not null
);

alter table public.payment_events enable row level security;
alter table public.license_status_history enable row level security;
alter table public.godfin_migration_evidence enable row level security;
revoke all on public.payment_events from public, anon, authenticated;
revoke all on public.license_status_history from public, anon, authenticated;
revoke all on public.godfin_migration_evidence from public, anon, authenticated;
grant all on public.payment_events to service_role;
grant all on public.license_status_history to service_role;
grant all on public.godfin_migration_evidence to service_role;

drop policy if exists "Users read their own licenses" on public.licenses;
create policy "Users read their own licenses"
  on public.licenses for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users read their own purchases" on public.purchases;
create policy "Users read their own purchases"
  on public.purchases for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users read their own credit balance" on public.credit_balances;
create policy "Users read their own credit balance"
  on public.credit_balances for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users read activations for their licenses"
  on public.license_activations;
create policy "Users read activations for their licenses"
  on public.license_activations for select to authenticated
  using (
    exists (
      select 1
      from public.licenses
      where public.licenses.id = public.license_activations.license_id
        and public.licenses.user_id = (select auth.uid())
    )
  );

create or replace function private.recompute_purchase_license_state(
  p_purchase_id uuid,
  p_source_event_id text default null
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_purchase public.purchases%rowtype;
  v_license public.licenses%rowtype;
  v_refund_total bigint := 0;
  v_charge_refund_total bigint := 0;
  v_refund_pending boolean := false;
  v_dispute_open boolean := false;
  v_dispute_lost boolean := false;
  v_payment_failed boolean := false;
  v_previous_status text;
  v_desired_status text := 'active';
  v_purchase_status text := 'paid';
  v_reason text := 'payment state reconciled';
begin
  select * into v_purchase
  from public.purchases
  where id = p_purchase_id
  for update;

  if v_purchase.id is null or v_purchase.license_id is null then
    return null;
  end if;

  select * into v_license
  from public.licenses
  where id = v_purchase.license_id
  for update;

  with latest_refunds as (
    select distinct on (coalesce(e.refund_id, e.object_id))
      e.amount,
      lower(coalesce(e.event_status, '')) as event_status
    from public.payment_events e
    where e.purchase_id = p_purchase_id
      and e.event_type in ('refund.created', 'refund.updated', 'refund.failed')
    order by coalesce(e.refund_id, e.object_id), e.occurred_at desc, e.created_at desc
  )
  select
    coalesce(sum(amount) filter (where event_status = 'succeeded'), 0),
    coalesce(bool_or(event_status in ('pending', 'requires_action')), false)
  into v_refund_total, v_refund_pending
  from latest_refunds;

  select coalesce(max(e.amount), 0)
  into v_charge_refund_total
  from public.payment_events e
  where e.purchase_id = p_purchase_id
    and e.event_type = 'charge.refunded';
  v_refund_total := greatest(v_refund_total, v_charge_refund_total);

  with latest_disputes as (
    select distinct on (coalesce(e.dispute_id, e.object_id))
      lower(coalesce(e.event_status, '')) as event_status
    from public.payment_events e
    where e.purchase_id = p_purchase_id
      and e.event_type in (
        'charge.dispute.created',
        'charge.dispute.updated',
        'charge.dispute.closed',
        'charge.dispute.funds_withdrawn',
        'charge.dispute.funds_reinstated'
      )
    order by coalesce(e.dispute_id, e.object_id), e.occurred_at desc, e.created_at desc
  )
  select
    coalesce(
      bool_or(event_status not in ('won', 'warning_closed', 'prevented')),
      false
    ),
    coalesce(bool_or(event_status = 'lost'), false)
  into v_dispute_open, v_dispute_lost
  from latest_disputes;

  select coalesce(
    (
      select e.event_type = 'checkout.session.async_payment_failed'
      from public.payment_events e
      where e.purchase_id = p_purchase_id
        and e.event_type in (
          'checkout.session.completed',
          'checkout.session.async_payment_succeeded',
          'checkout.session.async_payment_failed'
        )
      order by e.occurred_at desc, e.created_at desc
      limit 1
    ),
    false
  ) into v_payment_failed;

  if (v_refund_total > 0 and v_refund_total >= v_purchase.amount_total)
    or v_dispute_lost then
    v_desired_status := 'revoked';
    v_purchase_status := case
      when v_refund_total >= v_purchase.amount_total then 'refunded'
      else 'dispute_lost'
    end;
    v_reason := v_purchase_status;
  elsif v_refund_total > 0
    or v_refund_pending
    or v_dispute_open
    or v_payment_failed
    or v_purchase.pricing_review_reason is not null then
    v_desired_status := 'suspended';
    v_purchase_status := case
      when v_purchase.pricing_review_reason is not null then 'pricing_review'
      when v_refund_total > 0 then 'partially_refunded'
      when v_refund_pending then 'refund_pending'
      when v_dispute_open then 'disputed'
      else 'payment_failed'
    end;
    v_reason := v_purchase_status;
  end if;

  update public.purchases
  set status = v_purchase_status,
      refunded_amount = v_refund_total,
      updated_at = now()
  where id = p_purchase_id;

  if v_license.status is distinct from v_desired_status then
    v_previous_status := v_license.status;
    update public.licenses
    set status = v_desired_status,
        state_version = state_version + 1
    where id = v_license.id
    returning * into v_license;

    insert into public.license_status_history (
      license_id,
      previous_status,
      new_status,
      state_version,
      source_event_id,
      reason
    ) values (
      v_license.id,
      v_previous_status,
      v_desired_status,
      v_license.state_version,
      p_source_event_id,
      v_reason
    );
  end if;

  return v_desired_status;
end;
$$;

revoke all on function private.recompute_purchase_license_state(uuid, text)
  from public, anon, authenticated;

drop function if exists public.provision_purchase(
  text, uuid, text, bigint, text, text, text, text, bigint
);

create or replace function public.provision_purchase(
  p_checkout_session_id text,
  p_payment_intent_id text,
  p_charge_id text,
  p_stripe_customer_id text,
  p_user_id uuid,
  p_product_code text,
  p_amount_total bigint,
  p_currency text,
  p_license_tier text,
  p_license_hash text,
  p_license_last4 text,
  p_credits bigint,
  p_billing_country text,
  p_pricing_country text,
  p_pricing_version text,
  p_pricing_verified boolean,
  p_pricing_review_reason text
)
returns table (
  purchase_id uuid,
  license_id uuid,
  created boolean,
  email_sent_at timestamptz,
  license_status text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_purchase_id uuid;
  v_license_id uuid;
  v_email_sent_at timestamptz;
  v_license_status text;
begin
  if p_checkout_session_id is null
    or p_checkout_session_id = ''
    or p_user_id is null
    or p_amount_total is null
    or p_amount_total <= 0
    or lower(coalesce(p_currency, '')) not in ('inr', 'usd') then
    raise exception 'Invalid purchase provisioning input';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext(p_checkout_session_id));

  select p.id, p.license_id, p.email_sent_at
    into v_purchase_id, v_license_id, v_email_sent_at
  from public.purchases p
  where p.checkout_session_id = p_checkout_session_id;

  if v_purchase_id is not null then
    update public.purchases
    set payment_intent_id = coalesce(payment_intent_id, p_payment_intent_id),
        charge_id = coalesce(charge_id, p_charge_id),
        stripe_customer_id = coalesce(stripe_customer_id, p_stripe_customer_id),
        billing_country = coalesce(upper(p_billing_country), billing_country),
        pricing_country = coalesce(upper(p_pricing_country), pricing_country),
        pricing_version = coalesce(p_pricing_version, pricing_version),
        pricing_review_reason = case
          when p_pricing_verified then null
          else left(coalesce(p_pricing_review_reason, 'pricing verification failed'), 200)
        end,
        updated_at = now()
    where id = v_purchase_id;
    update public.payment_events e
    set purchase_id = v_purchase_id,
        mapped_at = now()
    where e.purchase_id is null
      and (
        (p_payment_intent_id is not null and e.payment_intent_id = p_payment_intent_id)
        or (p_charge_id is not null and e.charge_id = p_charge_id)
        or e.checkout_session_id = p_checkout_session_id
      );
    v_license_status := private.recompute_purchase_license_state(v_purchase_id, null);
    return query
      select v_purchase_id, v_license_id, false, v_email_sent_at, v_license_status;
    return;
  end if;

  if coalesce(p_license_tier, '') not in ('pro', 'max')
    or p_license_hash is null
    or length(p_license_hash) <> 64
    or p_license_last4 is null
    or length(p_license_last4) <> 4
    or coalesce(p_product_code, '') <> p_license_tier
    or coalesce(p_credits, -1) <> 0 then
    raise exception 'Invalid lifetime-license provisioning input';
  end if;

  v_license_status := case when p_pricing_verified then 'active' else 'suspended' end;
  insert into public.licenses (
    user_id, tier, key_hash, key_last4, status, state_version
  ) values (
    p_user_id, p_license_tier, p_license_hash, p_license_last4,
    v_license_status, 1
  ) returning id into v_license_id;

  insert into public.purchases (
    checkout_session_id,
    payment_intent_id,
    charge_id,
    stripe_customer_id,
    user_id,
    product_code,
    amount_total,
    currency,
    license_id,
    credits,
    billing_country,
    pricing_country,
    pricing_version,
    pricing_review_reason,
    status
  ) values (
    p_checkout_session_id,
    p_payment_intent_id,
    p_charge_id,
    p_stripe_customer_id,
    p_user_id,
    p_product_code,
    p_amount_total,
    lower(p_currency),
    v_license_id,
    0,
    upper(p_billing_country),
    upper(p_pricing_country),
    p_pricing_version,
    case
      when p_pricing_verified then null
      else left(coalesce(p_pricing_review_reason, 'pricing verification failed'), 200)
    end,
    case when p_pricing_verified then 'paid' else 'pricing_review' end
  ) returning id into v_purchase_id;

  insert into public.license_status_history (
    license_id, previous_status, new_status, state_version, reason
  ) values (
    v_license_id, null, v_license_status, 1,
    case when p_pricing_verified then 'purchase provisioned' else 'pricing review required' end
  );

  update public.payment_events e
  set purchase_id = v_purchase_id,
      mapped_at = now()
  where e.purchase_id is null
    and (
      (p_payment_intent_id is not null and e.payment_intent_id = p_payment_intent_id)
      or (p_charge_id is not null and e.charge_id = p_charge_id)
      or e.checkout_session_id = p_checkout_session_id
    );
  v_license_status := private.recompute_purchase_license_state(v_purchase_id, null);

  return query
    select v_purchase_id, v_license_id, true, null::timestamptz, v_license_status;
end;
$$;

revoke all on function public.provision_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text, bigint,
  text, text, text, boolean, text
) from public, anon, authenticated;
grant execute on function public.provision_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text, bigint,
  text, text, text, boolean, text
) to service_role;

create or replace function public.record_payment_event(
  p_stripe_event_id text,
  p_event_type text,
  p_object_id text,
  p_checkout_session_id text,
  p_payment_intent_id text,
  p_charge_id text,
  p_refund_id text,
  p_dispute_id text,
  p_amount bigint,
  p_currency text,
  p_event_status text,
  p_reason text,
  p_payload_sha256 text,
  p_occurred_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_purchase_id uuid;
  v_created boolean := false;
  v_license_status text;
begin
  if p_stripe_event_id is null
    or p_stripe_event_id = ''
    or coalesce(p_event_type, '') not in (
      'checkout.session.completed',
      'checkout.session.async_payment_succeeded',
      'checkout.session.async_payment_failed',
      'refund.created',
      'refund.updated',
      'refund.failed',
      'charge.refunded',
      'charge.dispute.created',
      'charge.dispute.updated',
      'charge.dispute.closed',
      'charge.dispute.funds_withdrawn',
      'charge.dispute.funds_reinstated'
    )
    or coalesce(p_payload_sha256, '') !~ '^[0-9a-f]{64}$'
    or p_occurred_at is null then
    raise exception 'Invalid payment event input';
  end if;
  select p.id into v_purchase_id
  from public.purchases p
  where (p_checkout_session_id is not null and p.checkout_session_id = p_checkout_session_id)
     or (p_payment_intent_id is not null and p.payment_intent_id = p_payment_intent_id)
     or (p_charge_id is not null and p.charge_id = p_charge_id)
  order by p.created_at desc
  limit 1;

  insert into public.payment_events (
    stripe_event_id,
    event_type,
    object_id,
    checkout_session_id,
    payment_intent_id,
    charge_id,
    refund_id,
    dispute_id,
    purchase_id,
    amount,
    currency,
    event_status,
    reason,
    payload_sha256,
    occurred_at,
    mapped_at
  ) values (
    p_stripe_event_id,
    p_event_type,
    p_object_id,
    p_checkout_session_id,
    p_payment_intent_id,
    p_charge_id,
    p_refund_id,
    p_dispute_id,
    v_purchase_id,
    p_amount,
    lower(p_currency),
    left(p_event_status, 80),
    left(p_reason, 200),
    p_payload_sha256,
    p_occurred_at,
    case when v_purchase_id is null then null else now() end
  ) on conflict (stripe_event_id) do nothing;
  v_created := found;

  if not v_created then
    select e.purchase_id into v_purchase_id
    from public.payment_events e
    where e.stripe_event_id = p_stripe_event_id;
  end if;
  if v_purchase_id is not null then
    v_license_status := private.recompute_purchase_license_state(
      v_purchase_id,
      p_stripe_event_id
    );
  end if;
  return jsonb_build_object(
    'created', v_created,
    'mapped', v_purchase_id is not null,
    'purchase_id', v_purchase_id,
    'license_status', v_license_status
  );
end;
$$;

revoke all on function public.record_payment_event(
  text, text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
) from public, anon, authenticated;
grant execute on function public.record_payment_event(
  text, text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
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

alter function public.provision_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text, bigint,
  text, text, text, boolean, text
) set search_path = '';
alter function public.record_payment_event(
  text, text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
) set search_path = '';
alter function public.verify_license(text, text, text, text, integer)
  set search_path = '';
