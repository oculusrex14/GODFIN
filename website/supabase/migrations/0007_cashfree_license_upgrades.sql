alter table public.purchases
  add column if not exists purchase_kind text not null default 'base',
  add column if not exists previous_tier text,
  add column if not exists target_tier text,
  add column if not exists upgrade_license_id uuid references public.licenses(id)
    on delete set null;

update public.purchases
set target_tier = case
  when product_code in ('pro', 'max') then product_code
  else target_tier
end
where target_tier is null;

alter table public.purchases
  drop constraint if exists purchases_purchase_kind_check,
  add constraint purchases_purchase_kind_check
    check (purchase_kind in ('base', 'upgrade')),
  drop constraint if exists purchases_previous_tier_check,
  add constraint purchases_previous_tier_check
    check (previous_tier is null or previous_tier in ('pro', 'max')),
  drop constraint if exists purchases_target_tier_check,
  add constraint purchases_target_tier_check
    check (target_tier is null or target_tier in ('pro', 'max')),
  drop constraint if exists purchases_upgrade_shape_check,
  add constraint purchases_upgrade_shape_check check (
    (
      purchase_kind = 'base'
      and previous_tier is null
      and upgrade_license_id is null
    )
    or (
      purchase_kind = 'upgrade'
      and product_code = 'pro_to_max'
      and previous_tier = 'pro'
      and target_tier = 'max'
      and upgrade_license_id is not null
      and upgrade_license_id = license_id
    )
  );

create unique index if not exists purchases_one_base_per_license_idx
  on public.purchases(license_id)
  where license_id is not null and purchase_kind = 'base';
create index if not exists purchases_upgrade_license_idx
  on public.purchases(upgrade_license_id, created_at desc)
  where purchase_kind = 'upgrade';

alter table public.license_status_history
  add column if not exists previous_tier text,
  add column if not exists new_tier text,
  add column if not exists source_purchase_id uuid
    references public.purchases(id) on delete set null;

alter table public.license_status_history
  drop constraint if exists license_status_history_previous_tier_check,
  add constraint license_status_history_previous_tier_check
    check (previous_tier is null or previous_tier in ('pro', 'max')),
  drop constraint if exists license_status_history_new_tier_check,
  add constraint license_status_history_new_tier_check
    check (new_tier is null or new_tier in ('pro', 'max'));

create or replace function private.cashfree_purchase_state(
  p_purchase_id uuid
)
returns table (
  purchase_status text,
  refund_total bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_purchase public.purchases%rowtype;
  v_refund_total bigint := 0;
  v_refund_pending boolean := false;
  v_dispute_open boolean := false;
  v_dispute_lost boolean := false;
begin
  select * into v_purchase
  from public.purchases
  where id = p_purchase_id
    and payment_provider = 'cashfree';

  if v_purchase.id is null then
    return query select null::text, 0::bigint;
    return;
  end if;

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

  purchase_status := 'paid';
  if v_refund_total >= v_purchase.amount_total or v_dispute_lost then
    purchase_status := case
      when v_refund_total >= v_purchase.amount_total then 'refunded'
      else 'dispute_lost'
    end;
  elsif v_refund_total > 0 then
    purchase_status := 'partially_refunded';
  elsif v_refund_pending then
    purchase_status := 'refund_pending';
  elsif v_dispute_open then
    purchase_status := 'disputed';
  elsif v_purchase.pricing_review_reason is not null then
    purchase_status := 'pricing_review';
  end if;
  refund_total := v_refund_total;
  return next;
end;
$$;

revoke all on function private.cashfree_purchase_state(uuid)
  from public, anon, authenticated;

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
  v_purchase_status text;
  v_refund_total bigint := 0;
  v_base_status text;
  v_base_tier text;
  v_has_upgrade boolean := false;
  v_has_paid_upgrade boolean := false;
  v_previous_status text;
  v_previous_tier text;
  v_desired_status text;
  v_desired_tier text;
  v_reason text;
begin
  select * into v_purchase
  from public.purchases
  where id = p_purchase_id
    and payment_provider = 'cashfree'
  for update;

  if v_purchase.id is null or v_purchase.license_id is null then
    return null;
  end if;

  select state.purchase_status, state.refund_total
    into v_purchase_status, v_refund_total
  from private.cashfree_purchase_state(p_purchase_id) state;

  update public.purchases
  set status = v_purchase_status,
      refunded_amount = v_refund_total,
      updated_at = now()
  where id = p_purchase_id;

  select * into v_license
  from public.licenses
  where id = v_purchase.license_id
  for update;

  select p.status, coalesce(p.target_tier, p.product_code)
    into v_base_status, v_base_tier
  from public.purchases p
  where p.license_id = v_license.id
    and p.purchase_kind = 'base'
  order by p.created_at asc
  limit 1;

  select
    exists (
      select 1 from public.purchases p
      where p.license_id = v_license.id and p.purchase_kind = 'upgrade'
    ),
    exists (
      select 1 from public.purchases p
      where p.license_id = v_license.id
        and p.purchase_kind = 'upgrade'
        and p.status = 'paid'
    )
  into v_has_upgrade, v_has_paid_upgrade;

  if v_base_status = 'paid' then
    v_desired_status := 'active';
    v_desired_tier := case
      when v_base_tier = 'max' or v_has_paid_upgrade then 'max'
      else 'pro'
    end;
    v_reason := case
      when v_has_paid_upgrade then 'cashfree upgrade active'
      when v_base_tier = 'max' then 'cashfree max purchase active'
      else 'cashfree pro purchase active'
    end;
  elsif v_base_status in (
    'pricing_review', 'partially_refunded', 'refund_pending', 'disputed'
  ) or v_has_upgrade then
    v_desired_status := 'suspended';
    v_desired_tier := coalesce(v_base_tier, v_license.tier);
    v_reason := 'base purchase requires review';
  else
    v_desired_status := 'revoked';
    v_desired_tier := coalesce(v_base_tier, v_license.tier);
    v_reason := 'base purchase is no longer active';
  end if;

  if v_license.status is distinct from v_desired_status
    or v_license.tier is distinct from v_desired_tier then
    v_previous_status := v_license.status;
    v_previous_tier := v_license.tier;
    update public.licenses
    set status = v_desired_status,
        tier = v_desired_tier,
        state_version = state_version + 1
    where id = v_license.id
    returning * into v_license;

    insert into public.license_status_history (
      license_id,
      previous_status,
      new_status,
      state_version,
      source_event_id,
      reason,
      previous_tier,
      new_tier,
      source_purchase_id
    ) values (
      v_license.id,
      v_previous_status,
      v_desired_status,
      v_license.state_version,
      p_source_event_id,
      v_reason,
      v_previous_tier,
      v_desired_tier,
      p_purchase_id
    );
  end if;

  return v_desired_status;
end;
$$;

revoke all on function private.recompute_cashfree_purchase_license_state(uuid, text)
  from public, anon, authenticated;

drop function if exists public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text
);

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
  p_pricing_review_reason text,
  p_purchase_kind text,
  p_upgrade_license_id uuid
)
returns table (
  purchase_id uuid,
  license_id uuid,
  created boolean,
  email_sent_at timestamptz,
  license_status text,
  effective_tier text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_purchase public.purchases%rowtype;
  v_license public.licenses%rowtype;
  v_license_id uuid;
  v_license_status text;
  v_effective_tier text;
begin
  if coalesce(p_order_id, '') !~ '^godfin_[0-9a-f-]{36}$'
    or coalesce(p_cf_order_id, '') = ''
    or coalesce(p_cf_payment_id, '') = ''
    or p_user_id is null
    or p_amount_total is null
    or p_amount_total <= 0
    or lower(coalesce(p_currency, '')) not in ('inr', 'usd')
    or coalesce(p_purchase_kind, '') not in ('base', 'upgrade') then
    raise exception 'Invalid Cashfree purchase provisioning input';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('cashfree-user:' || p_user_id::text)
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('cashfree:' || p_order_id)
  );

  select * into v_purchase
  from public.purchases p
  where p.payment_provider = 'cashfree'
    and p.provider_order_id = p_order_id;

  if v_purchase.id is not null then
    if v_purchase.user_id <> p_user_id
      or v_purchase.product_code <> p_product_code
      or v_purchase.amount_total <> p_amount_total
      or v_purchase.currency <> lower(p_currency)
      or v_purchase.purchase_kind <> p_purchase_kind
      or v_purchase.upgrade_license_id is distinct from p_upgrade_license_id then
      raise exception 'Cashfree order identity does not match the existing purchase';
    end if;
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
    where id = v_purchase.id;
    update public.payment_events e
    set purchase_id = v_purchase.id,
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
      v_purchase.id,
      null
    );
    select tier into v_effective_tier
    from public.licenses where id = v_purchase.license_id;
    return query select
      v_purchase.id,
      v_purchase.license_id,
      false,
      v_purchase.email_sent_at,
      v_license_status,
      v_effective_tier;
    return;
  end if;

  if p_purchase_kind = 'base' then
    if coalesce(p_product_code, '') not in ('pro', 'max')
      or p_license_tier <> p_product_code
      or p_upgrade_license_id is not null
      or coalesce(p_license_hash, '') !~ '^[0-9a-f]{64}$'
      or coalesce(p_license_last4, '') !~ '^[A-Z0-9]{4}$' then
      raise exception 'Invalid Cashfree base-license input';
    end if;
    if exists (
      select 1 from public.licenses l
      where l.user_id = p_user_id and l.kind = 'purchase'
    ) then
      raise exception 'A purchase license already exists for this account';
    end if;
    v_license_status := case when p_pricing_verified then 'active' else 'suspended' end;
    insert into public.licenses (
      user_id, tier, key_hash, key_last4, kind, status, state_version
    ) values (
      p_user_id, p_license_tier, p_license_hash, p_license_last4,
      'purchase', v_license_status, 1
    ) returning * into v_license;
    v_license_id := v_license.id;
  else
    if p_product_code <> 'pro_to_max'
      or p_license_tier <> 'max'
      or p_upgrade_license_id is null
      or p_license_hash is not null
      or p_license_last4 is not null then
      raise exception 'Invalid Cashfree upgrade input';
    end if;
    select * into v_license
    from public.licenses l
    where l.id = p_upgrade_license_id
      and l.user_id = p_user_id
      and l.kind = 'purchase'
    for update;
    if v_license.id is null
      or v_license.status <> 'active'
      or v_license.tier <> 'pro'
      or not exists (
        select 1 from public.purchases p
        where p.license_id = v_license.id
          and p.purchase_kind = 'base'
          and p.status = 'paid'
      )
      or exists (
        select 1 from public.purchases p
        where p.license_id = v_license.id
          and p.purchase_kind = 'upgrade'
          and p.status in ('paid', 'pricing_review', 'partially_refunded', 'refund_pending', 'disputed')
      ) then
      raise exception 'This license is not eligible for a Pro to Max upgrade';
    end if;
    v_license_id := v_license.id;
  end if;

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
    provider_customer_id,
    purchase_kind,
    previous_tier,
    target_tier,
    upgrade_license_id
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
    p_cf_customer_id,
    p_purchase_kind,
    case when p_purchase_kind = 'upgrade' then 'pro' else null end,
    p_license_tier,
    p_upgrade_license_id
  ) returning * into v_purchase;

  if p_purchase_kind = 'base' then
    insert into public.license_status_history (
      license_id,
      previous_status,
      new_status,
      state_version,
      reason,
      previous_tier,
      new_tier,
      source_purchase_id
    ) values (
      v_license_id,
      null,
      v_license_status,
      1,
      case
        when p_pricing_verified then 'cashfree purchase provisioned'
        else 'cashfree pricing review required'
      end,
      null,
      p_license_tier,
      v_purchase.id
    );
  end if;

  update public.payment_events e
  set purchase_id = v_purchase.id,
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
    v_purchase.id,
    null
  );
  select tier into v_effective_tier
  from public.licenses where id = v_license_id;

  return query select
    v_purchase.id,
    v_license_id,
    true,
    null::timestamptz,
    v_license_status,
    v_effective_tier;
end;
$$;

revoke all on function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text, text, uuid
) from public, anon, authenticated;
grant execute on function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text, text, uuid
) to service_role;

alter function private.cashfree_purchase_state(uuid) set search_path = '';
alter function private.recompute_cashfree_purchase_license_state(uuid, text)
  set search_path = '';
alter function public.provision_cashfree_purchase(
  text, text, text, text, uuid, text, bigint, text, text, text, text,
  text, text, text, boolean, text, text, uuid
) set search_path = '';
