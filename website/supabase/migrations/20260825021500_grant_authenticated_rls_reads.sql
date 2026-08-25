-- RLS policies do not grant table privileges by themselves. Keep website
-- account reads explicit and read-only on every fresh Supabase deployment.
revoke all on table
  public.licenses,
  public.purchases,
  public.credit_balances,
  public.license_activations
from anon, authenticated;

grant select on table
  public.licenses,
  public.purchases,
  public.credit_balances,
  public.license_activations
to authenticated;

comment on table public.licenses is
  'Lifetime entitlements. Authenticated owners have RLS-filtered read-only access.';
comment on table public.purchases is
  'Provider purchase ledger. Authenticated owners have RLS-filtered read-only access.';
comment on table public.credit_balances is
  'Separate hosted-credit balances. Authenticated owners have RLS-filtered read-only access.';
comment on table public.license_activations is
  'Installation activations. Authenticated owners have RLS-filtered read-only access.';
