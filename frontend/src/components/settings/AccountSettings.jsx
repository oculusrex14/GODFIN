import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';

import {
  createAccount,
  deactivateAccount,
  fetchAllAccounts,
  fetchParserProfiles,
  fetchSenderMappings,
  replaceSenderMappings,
  updateAccount,
} from '../../api/client';
import { useConfirm } from '../ConfirmDialog';
import { useToast } from '../../context/ToastContext';

const EMPTY_FORM = {
  bank: 'HDFC',
  account_type: 'savings',
  last_4_digits: '',
  nickname: '',
  sender_pattern: '',
  parser_profile: 'hdfc_savings',
};

function accountLabel(account) {
  return account.nickname
    || `${account.bank} ${account.account_type.replace('_', ' ')} ••••${account.last_4_digits}`;
}

export default function AccountSettings() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { confirm, ConfirmDialog } = useConfirm();
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts', 'all'],
    queryFn: fetchAllAccounts,
  });
  const { data: mappings = [] } = useQuery({
    queryKey: ['senderMappings'],
    queryFn: fetchSenderMappings,
  });
  const { data: profiles = [] } = useQuery({
    queryKey: ['parserProfiles'],
    queryFn: fetchParserProfiles,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['accounts'] }),
      queryClient.invalidateQueries({ queryKey: ['senderMappings'] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        bank: form.bank,
        account_type: form.account_type,
        last_4_digits: form.last_4_digits,
        nickname: form.nickname || null,
        ...(editingId ? { is_active: true } : {}),
      };
      const account = editingId
        ? await updateAccount(editingId, payload)
        : await createAccount(payload);

      if (form.sender_pattern.trim()) {
        const pattern = form.sender_pattern.trim().toLowerCase();
        const nextMappings = mappings
          .filter(item => item.sender_pattern !== pattern)
          .concat({
            sender_pattern: pattern,
            parser_profile: form.parser_profile,
            account_id: account.id,
          });
        await replaceSenderMappings(nextMappings);
      }
      return account;
    },
    onSuccess: async () => {
      await refresh();
      setEditingId(null);
      setForm(EMPTY_FORM);
      addToast('Account settings saved.', 'success');
    },
    onError: error => addToast(error?.message || 'Could not save account.', 'error'),
  });

  const deactivateMutation = useMutation({
    mutationFn: deactivateAccount,
    onSuccess: async () => {
      await refresh();
      addToast('Account deactivated. Existing transactions were preserved.', 'success');
    },
    onError: error => addToast(error?.message || 'Could not deactivate account.', 'error'),
  });

  const startEdit = (account) => {
    const mapping = mappings.find(item => item.account_id === account.id);
    setEditingId(account.id);
    setForm({
      bank: account.bank,
      account_type: account.account_type,
      last_4_digits: account.last_4_digits,
      nickname: account.nickname || '',
      sender_pattern: mapping?.sender_pattern || '',
      parser_profile: mapping?.parser_profile
        || (account.account_type === 'credit_card' ? 'hdfc_credit' : 'hdfc_savings'),
    });
  };

  const requestDeactivate = async (account) => {
    const accepted = await confirm({
      title: 'Deactivate account?',
      message: `${accountLabel(account)} will stop appearing in imports and new-entry forms. Existing transactions stay intact.`,
      confirmLabel: 'Deactivate',
      cancelLabel: 'Keep account',
      danger: true,
    });
    if (accepted) deactivateMutation.mutate(account.id);
  };

  const set = (key, value) => {
    setForm(current => ({ ...current, [key]: value }));
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        {accounts.map(account => (
          <div
            key={account.id}
            className={`rounded-[14px] border p-3 flex flex-wrap items-center gap-3 ${
              account.is_active
                ? 'border-white/[0.1] bg-white/[0.04]'
                : 'border-white/[0.05] bg-white/[0.02] opacity-55'
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="text-white/70 text-sm truncate">{accountLabel(account)}</div>
              <div className="text-white/25 text-xs mt-0.5">
                {account.bank} · {account.account_type.replace('_', ' ')} · ••••{account.last_4_digits}
                {!account.is_active && ' · inactive'}
              </div>
            </div>
            <button
              onClick={() => startEdit(account)}
              className="min-w-11 min-h-11 grid place-items-center rounded-xl text-white/35 hover:text-white/70 hover:bg-white/[0.06]"
              aria-label={`Edit ${accountLabel(account)}`}
            >
              <Pencil size={15} />
            </button>
            {account.is_active && (
              <button
                onClick={() => requestDeactivate(account)}
                className="min-w-11 min-h-11 grid place-items-center rounded-xl text-white/35 hover:text-rose-300 hover:bg-rose-400/[0.06]"
                aria-label={`Deactivate ${accountLabel(account)}`}
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="rounded-[16px] border border-white/[0.1] bg-white/[0.035] p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <div className="text-white/70 text-sm">
              {editingId ? 'Edit account' : 'Add account'}
            </div>
            <div className="text-white/25 text-xs">
              Non-HDFC accounts require Pro or Max. Sender matching stays in local SQLite.
            </div>
          </div>
          {editingId && (
            <button
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
              }}
              className="min-w-11 min-h-11 grid place-items-center rounded-xl text-white/35 hover:text-white/70"
              aria-label="Cancel account edit"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-white/35 text-xs">
            Bank
            <select
              value={form.bank}
              onChange={event => set('bank', event.target.value)}
              className="glass-input w-full mt-1 px-3 py-2 text-sm"
            >
              {['HDFC', 'SBI', 'ICICI', 'AXIS', 'KOTAK'].map(bank => (
                <option key={bank} value={bank}>{bank}</option>
              ))}
            </select>
          </label>
          <label className="text-white/35 text-xs">
            Account type
            <select
              value={form.account_type}
              onChange={event => {
                const value = event.target.value;
                setForm(current => ({
                  ...current,
                  account_type: value,
                  parser_profile: value === 'credit_card' ? 'hdfc_credit' : 'hdfc_savings',
                }));
              }}
              className="glass-input w-full mt-1 px-3 py-2 text-sm"
            >
              <option value="savings">Savings</option>
              <option value="credit_card">Credit card</option>
            </select>
          </label>
          <label className="text-white/35 text-xs">
            Last 4 digits
            <input
              value={form.last_4_digits}
              onChange={event => set('last_4_digits', event.target.value.replace(/\D/g, '').slice(0, 4))}
              inputMode="numeric"
              maxLength={4}
              className="glass-input w-full mt-1 px-3 py-2 text-sm"
              placeholder="1234"
            />
          </label>
          <label className="text-white/35 text-xs">
            Nickname
            <input
              value={form.nickname}
              onChange={event => set('nickname', event.target.value)}
              className="glass-input w-full mt-1 px-3 py-2 text-sm"
              placeholder="Salary account"
            />
          </label>
          <label className="text-white/35 text-xs sm:col-span-2">
            Gmail sender pattern (optional)
            <input
              value={form.sender_pattern}
              onChange={event => set('sender_pattern', event.target.value)}
              className="glass-input w-full mt-1 px-3 py-2 text-sm"
              placeholder="alerts@bank.example"
            />
          </label>
          {form.sender_pattern && (
            <label className="text-white/35 text-xs sm:col-span-2">
              Email parser profile
              <select
                value={form.parser_profile}
                onChange={event => set('parser_profile', event.target.value)}
                className="glass-input w-full mt-1 px-3 py-2 text-sm"
              >
                {profiles.map(profile => (
                  <option key={profile.profile} value={profile.profile}>
                    {profile.bank} · {profile.account_type.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <button
          onClick={() => saveMutation.mutate()}
          disabled={form.last_4_digits.length !== 4 || saveMutation.isPending}
          className="mt-4 min-h-11 px-4 rounded-xl bg-cyan-400/[0.14] border border-cyan-300/[0.18] text-cyan-100/80 text-sm disabled:opacity-40 inline-flex items-center gap-2"
        >
          {editingId ? <Check size={15} /> : <Plus size={15} />}
          {saveMutation.isPending ? 'Saving…' : editingId ? 'Save account' : 'Add account'}
        </button>
      </div>
      <ConfirmDialog />
    </div>
  );
}
