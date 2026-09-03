-- Capture beta-candidate context at registration without exposing the table to
-- browser roles. Existing RLS and service-role-only grants remain unchanged.

alter table public.waitlist_entries
  add column if not exists display_name text,
  add column if not exists occupation text,
  add column if not exists bank_count smallint,
  add column if not exists banks text[] not null default '{}';

alter table public.waitlist_entries
  alter column intended_use set default '',
  drop constraint if exists waitlist_entries_intended_use_check,
  drop constraint if exists waitlist_entries_display_name_check,
  drop constraint if exists waitlist_entries_occupation_check,
  drop constraint if exists waitlist_entries_bank_count_check,
  drop constraint if exists waitlist_entries_banks_count_check,
  add constraint waitlist_entries_intended_use_check
    check (char_length(intended_use) <= 1000),
  add constraint waitlist_entries_display_name_check
    check (display_name is null or char_length(display_name) between 2 and 100),
  add constraint waitlist_entries_occupation_check
    check (occupation is null or char_length(occupation) between 2 and 120),
  add constraint waitlist_entries_bank_count_check
    check (bank_count is null or bank_count between 0 and 25),
  add constraint waitlist_entries_banks_count_check
    check (coalesce(array_length(banks, 1), 0) <= 12);

comment on column public.waitlist_entries.display_name is
  'Name supplied for private beta selection and email communication.';
comment on column public.waitlist_entries.occupation is
  'Optional broad occupation supplied by the candidate.';
comment on column public.waitlist_entries.bank_count is
  'Optional count of banks used; no account identifiers are collected.';
comment on column public.waitlist_entries.banks is
  'Optional bank names only; no account identifiers are collected.';
