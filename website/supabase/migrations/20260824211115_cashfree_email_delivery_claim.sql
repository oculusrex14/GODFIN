alter table public.purchases
  add column if not exists email_claimed_at timestamptz;

create index if not exists purchases_pending_email_claim_idx
  on public.purchases(email_claimed_at)
  where email_sent_at is null;

comment on column public.purchases.email_claimed_at is
  'Short server-only lease preventing duplicate transactional email delivery.';
