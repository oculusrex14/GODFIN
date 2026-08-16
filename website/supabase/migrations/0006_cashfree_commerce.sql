alter table public.purchases
  add column if not exists payment_provider text not null default 'stripe'
    check (payment_provider in ('stripe', 'cashfree')),
  add column if not exists provider_order_id text,
  add column if not exists provider_order_reference_id text,
  add column if not exists provider_payment_id text,
  add column if not exists provider_customer_id text;

update public.purchases
set provider_order_id = coalesce(provider_order_id, checkout_session_id),
    provider_payment_id = coalesce(provider_payment_id, payment_intent_id),
    provider_customer_id = coalesce(provider_customer_id, stripe_customer_id)
where payment_provider = 'stripe';

create unique index if not exists purchases_provider_order_uidx
  on public.purchases(payment_provider, provider_order_id)
  where provider_order_id is not null;
create index if not exists purchases_provider_payment_idx
  on public.purchases(payment_provider, provider_payment_id)
  where provider_payment_id is not null;

alter table public.payment_events
  add column if not exists payment_provider text not null default 'stripe'
    check (payment_provider in ('stripe', 'cashfree')),
  add column if not exists provider_event_id text,
  add column if not exists provider_order_id text,
  add column if not exists provider_payment_id text,
  add column if not exists provider_refund_id text,
  add column if not exists provider_dispute_id text;

update public.payment_events
set provider_event_id = coalesce(provider_event_id, stripe_event_id),
    provider_order_id = coalesce(provider_order_id, checkout_session_id),
    provider_payment_id = coalesce(provider_payment_id, payment_intent_id),
    provider_refund_id = coalesce(provider_refund_id, refund_id),
    provider_dispute_id = coalesce(provider_dispute_id, dispute_id)
where payment_provider = 'stripe';

create unique index if not exists payment_events_provider_event_uidx
  on public.payment_events(payment_provider, provider_event_id)
  where provider_event_id is not null;
create index if not exists payment_events_provider_payment_idx
  on public.payment_events(payment_provider, provider_payment_id)
  where provider_payment_id is not null;

create or replace function private.recompute_cashfree_purchase_license_state(
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
  v_refund_pending boolean := false;
  v_dispute_open boolean := false;
  v_dispute_lost boolean := false;
  v_previous_status text;
  v_desired_status text := 'active';
  v_purchase_status text := 'paid';
  v_reason text := 'cashfree payment state reconciled';
begin
  select * into v_purchase
  from public.purchases
  where id = p_purchase_id
    and payment_provider = 'cashfree'
  for update;

  if v_purchase.id is null or v_purchase.license_id is null then
    return null;
  end if;

  select * into v_license
  from public.licenses
  where id = v_purchase.license_id
  for update;

  with latest_refunds as (
    select distinct on (coalesce(e.provider_refund_id, e.object_id))
      e.amount,
      upper(coalesce(e.event_status, '')) as event_status
    from public.payment_events e
    where e.purchase_id = p_purchase_id
      and e.payment_provider = 'cashfree'
      and e.event_type in ('REFUND_STATUS_WEBHOOK', 'AUTO_REFUND_STATUS_WEBHOOK')
    order by coalesce(e.provider_refund_id, e.object_id),
      e.occurred_at desc, e.created_at desc
  )
  select
    coalesce(sum(amount) filter (where event_status = 'SUCCESS'), 0),
    coalesce(bool_or(event_status in ('PENDING', 'IN_PROGRESS')), false)
  into v_refund_total, v_refund_pending
  from latest_refunds;

  with latest_disputes as (
    select distinct on (coalesce(e.provider_dispute_id, e.object_id))
      upper(coalesce(e.event_status, '')) as event_status
    from public.payment_events e
    where e.purchase_id = p_purchase_id
      and e.payment_provider = 'cashfree'
      and e.event_type in ('DISPUTE_CREATED', 'DISPUTE_UPDATED', 'DISPUTE_CLOSED')
    order by coalesce(e.provider_dispute_id, e.object_id),
      e.occurred_at desc, e.created_at desc
  )
  select
    coalesce(bool_or(event_status !~ '_MERCHANT_WON$'), false),
    coalesce(
      bool_or(
        event_status ~ '_MERCHANT_(LOST|ACCEPTED)$'
        or event_status ~ '_INSUFFICIENT_EVIDENCE$'
      ),
      false
    )
  into v_dispute_open, v_dispute_lost
  from latest_disputes;

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
    or v_purchase.pricing_review_reason is not null then
    v_desired_status := 'suspended';
    v_purchase_status := case
      when v_purchase.pricing_review_reason is not null then 'pricing_review'
      when v_refund_total > 0 then 'partially_refunded'
      when v_refund_pending then 'refund_pending'
      else 'disputed'
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

revoke all on function private.recompute_cashfree_purchase_license_state(uuid, text)
  from public, anon, authenticated;

create or replace function public.provision_cashfree_purchase(
  p_order_id text,
  p_cf_order_id text,
  p_cf_payment_id text,
  p_cf_customer_id text,
  p_user_id uuid,
  p_product_code text,
  p_amount_total bigint,
  p_currency text,
  p_license_tier text,
  p_license_hash text,
  p_license_last4 text,
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
  if coalesce(p_order_id, '') !~ '^godfin_[0-9a-f-]{36}$'
    or coalesce(p_cf_order_id, '') = ''
    or coalesce(p_cf_payment_id, '') = ''
    or p_user_id is null
    or p_amount_total is null
    or p_amount_total <= 0
    or lower(coalesce(p_currency, '')) not in ('inr', 'usd') then
    raise exception 'Invalid Cashfree purchase provisioning input';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('cashfree:' || p_order_id));

  select p.id, p.license_id, p.email_sent_at
    into v_purchase_id, v_license_id, v_email_sent_at
  from public.purchases p
  where p.payment_provider = 'cashfree'
    and p.provider_order_id = p_order_id;

  if v_purchase_id is not null then
    update public.purchases
    set provider_order_reference_id = coalesce(provider_order_reference_id, p_cf_order_id),
        provider_payment_id = coalesce(provider_payment_id, p_cf_payment_id),
        provider_customer_id = coalesce(provider_customer_id, p_cf_customer_id),
        payment_intent_id = coalesce(payment_intent_id, 'cashfree:' || p_cf_payment_id),
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
      and e.payment_provider = 'cashfree'
      and (
        e.provider_payment_id = p_cf_payment_id
        or (
          e.event_type = 'PAYMENT_SUCCESS_WEBHOOK'
          and e.provider_order_id = p_order_id
        )
      );
    v_license_status := private.recompute_cashfree_purchase_license_state(
      v_purchase_id,
      null
    );
    return query
      select v_purchase_id, v_license_id, false, v_email_sent_at, v_license_status;
    return;
  end if;

  if coalesce(p_license_tier, '') not in ('pro', 'max')
    or coalesce(p_product_code, '') <> p_license_tier
    or coalesce(p_license_hash, '') !~ '^[0-9a-f]{64}$'
    or coalesce(p_license_last4, '') !~ '^[A-Z0-9]{4}$' then
    raise exception 'Invalid Cashfree lifetime-license input';
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
    status,
    payment_provider,
    provider_order_id,
    provider_order_reference_id,
    provider_payment_id,
    provider_customer_id
  ) values (
    p_order_id,
    'cashfree:' || p_cf_payment_id,
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
    case when p_pricing_verified then 'paid' else 'pricing_review' end,
    'cashfree',
    p_order_id,
    p_cf_order_id,
    p_cf_payment_id,
    p_cf_customer_id
  ) returning id into v_purchase_id;

  insert into public.license_status_history (
    license_id, previous_status, new_status, state_version, reason
  ) values (
    v_license_id, null, v_license_status, 1,
    case
      when p_pricing_verified then 'cashfree purchase provisioned'
      else 'cashfree pricing review required'
    end
  );

  update public.payment_events e
  set purchase_id = v_purchase_id,
      mapped_at = now()
  where e.purchase_id is null
    and e.payment_provider = 'cashfree'
    and (
      e.provider_payment_id = p_cf_payment_id
      or (
        e.event_type = 'PAYMENT_SUCCESS_WEBHOOK'
        and e.provider_order_id = p_order_id
      )
    );
  v_license_status := private.recompute_cashfree_purchase_license_state(
    v_purchase_id,
    null
  );

  return query
    select v_purchase_id, v_license_id, true, null::timestamptz, v_license_status;
end;
$$;

revoke all on function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text
) from public, anon, authenticated;
grant execute on function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text
) to service_role;

create or replace function public.record_cashfree_payment_event(
  p_provider_event_id text,
  p_event_type text,
  p_object_id text,
  p_provider_order_id text,
  p_provider_payment_id text,
  p_provider_refund_id text,
  p_provider_dispute_id text,
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
  if coalesce(p_provider_event_id, '') = ''
    or coalesce(p_event_type, '') not in (
      'PAYMENT_SUCCESS_WEBHOOK',
      'PAYMENT_FAILED_WEBHOOK',
      'PAYMENT_USER_DROPPED_WEBHOOK',
      'REFUND_STATUS_WEBHOOK',
      'AUTO_REFUND_STATUS_WEBHOOK',
      'DISPUTE_CREATED',
      'DISPUTE_UPDATED',
      'DISPUTE_CLOSED'
    )
    or coalesce(p_payload_sha256, '') !~ '^[0-9a-f]{64}$'
    or p_occurred_at is null then
    raise exception 'Invalid Cashfree payment event input';
  end if;

  if p_provider_payment_id is not null then
    select p.id into v_purchase_id
    from public.purchases p
    where p.payment_provider = 'cashfree'
      and p.provider_payment_id = p_provider_payment_id
    order by p.created_at desc
    limit 1;
  end if;

  insert into public.payment_events (
    stripe_event_id,
    event_type,
    object_id,
    checkout_session_id,
    payment_intent_id,
    refund_id,
    dispute_id,
    purchase_id,
    amount,
    currency,
    event_status,
    reason,
    payload_sha256,
    occurred_at,
    mapped_at,
    payment_provider,
    provider_event_id,
    provider_order_id,
    provider_payment_id,
    provider_refund_id,
    provider_dispute_id
  ) values (
    p_provider_event_id,
    p_event_type,
    p_object_id,
    p_provider_order_id,
    case
      when p_provider_payment_id is null then null
      else 'cashfree:' || p_provider_payment_id
    end,
    p_provider_refund_id,
    p_provider_dispute_id,
    v_purchase_id,
    p_amount,
    lower(p_currency),
    left(p_event_status, 80),
    left(p_reason, 200),
    p_payload_sha256,
    p_occurred_at,
    case when v_purchase_id is null then null else now() end,
    'cashfree',
    p_provider_event_id,
    p_provider_order_id,
    p_provider_payment_id,
    p_provider_refund_id,
    p_provider_dispute_id
  ) on conflict (stripe_event_id) do nothing;
  v_created := found;

  if not v_created then
    select e.purchase_id into v_purchase_id
    from public.payment_events e
    where e.stripe_event_id = p_provider_event_id;
  end if;
  if v_purchase_id is not null then
    v_license_status := private.recompute_cashfree_purchase_license_state(
      v_purchase_id,
      p_provider_event_id
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

revoke all on function public.record_cashfree_payment_event(
  text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
) from public, anon, authenticated;
grant execute on function public.record_cashfree_payment_event(
  text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
) to service_role;

alter function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text
) set search_path = '';
alter function public.record_cashfree_payment_event(
  text, text, text, text, text, text, text, bigint, text, text, text,
  text, timestamptz
) set search_path = '';
