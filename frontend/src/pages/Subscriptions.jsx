import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import {
  CreditCard, Plus, Trash2, X, Pause, Play, ArrowRightLeft, Pencil,
  Check, Clock3, RefreshCw, BellRing,
} from 'lucide-react';
import {
  fetchSubscriptions, createSubscription, updateSubscription, deleteSubscription,
  fetchSubscriptionStats, fetchSubscriptionSuggestions, scanSubscriptionSuggestions,
  decideSubscriptionSuggestion, fetchSubscriptionReminders, refreshExchangeRates,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import { useToast } from '../context/ToastContext';

function formatINR(amount) {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatCurrency(amount, currency) {
  if (amount == null) return '--';
  const opts = { minimumFractionDigits: 0, maximumFractionDigits: 0 };
  if (currency === 'USD') return `$${amount.toLocaleString('en-US', opts)}`;
  if (currency === 'EUR') return `€${amount.toLocaleString('en-US', opts)}`;
  if (currency === 'GBP') return `£${amount.toLocaleString('en-US', opts)}`;
  return formatINR(amount);
}

const FREQUENCY_LABELS = { monthly: 'Monthly', quarterly: 'Quarterly', annual: 'Annual' };
const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP'];

export default function Subscriptions() {
  const queryClient = useQueryClient();
  const { addToast: showToast } = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [editSub, setEditSub] = useState(null);
  const [form, setForm] = useState({
    name: '', amount: '', currency: 'INR', frequency: 'monthly', category: '', subcategory: '', next_payment_date: '', notes: '',
  });
  const [editForm, setEditForm] = useState({
    name: '', amount: '', currency: 'INR', frequency: 'monthly', category: '', subcategory: '', next_payment_date: '', notes: '',
  });

  const { data: subs = [] } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => fetchSubscriptions(),
  });

  const { data: stats } = useQuery({
    queryKey: ['subscriptionStats'],
    queryFn: fetchSubscriptionStats,
  });

  const { data: suggestions = [] } = useQuery({
    queryKey: ['subscriptionSuggestions'],
    queryFn: () => fetchSubscriptionSuggestions(false),
  });

  const { data: reminderData } = useQuery({
    queryKey: ['subscriptionReminders'],
    queryFn: () => fetchSubscriptionReminders(7),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    queryClient.invalidateQueries({ queryKey: ['subscriptionStats'] });
    queryClient.invalidateQueries({ queryKey: ['subscriptionReminders'] });
  };

  const scanMutation = useMutation({
    mutationFn: scanSubscriptionSuggestions,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subscriptionSuggestions'] }),
  });

  const rateRefreshMutation = useMutation({
    mutationFn: refreshExchangeRates,
    onSuccess: (result) => {
      invalidate();
      if (result?.fx?.status === 'unavailable') {
        showToast('Could not refresh rates while offline. Saved rates remain unchanged.', 'error');
      } else if (result?.fx?.status === 'not_required') {
        showToast('No foreign-currency subscriptions need rates');
      } else {
        showToast(`Saved verified rates for ${result?.updated || 0} subscription${result?.updated === 1 ? '' : 's'}`);
      }
    },
    onError: (err) => showToast(err?.message || 'Could not refresh currency rates', 'error'),
  });

  const suggestionMutation = useMutation({
    mutationFn: decideSubscriptionSuggestion,
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['subscriptionSuggestions'] });
    },
  });

  const createMutation = useMutation({
    mutationFn: createSubscription,
    onSuccess: () => {
      invalidate();
      setAddOpen(false);
      setForm({ name: '', amount: '', currency: 'INR', frequency: 'monthly', category: '', subcategory: '', next_payment_date: '', notes: '' });
      showToast('Subscription added');
    },
    onError: (err) => showToast(err?.message || 'Failed to create', 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSubscription,
    onSuccess: () => { invalidate(); showToast('Subscription deleted'); },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }) => updateSubscription({ id, is_active }),
    onSuccess: () => invalidate(),
  });

  const editMutation = useMutation({
    mutationFn: (data) => updateSubscription(data),
    onSuccess: () => {
      invalidate();
      setEditSub(null);
      showToast('Subscription updated');
    },
    onError: (err) => showToast(err?.message || 'Failed to update', 'error'),
  });

  const openEdit = (sub) => {
    setEditForm({
      name: sub.name,
      amount: String(sub.amount),
      currency: sub.currency || 'INR',
      frequency: sub.frequency,
      category: sub.category || '',
      subcategory: sub.subcategory || '',
      next_payment_date: sub.next_payment_date || '',
      notes: sub.notes || '',
    });
    setEditSub(sub);
  };

  const activeSubs = subs.filter(s => s.is_active);
  const inactiveSubs = subs.filter(s => !s.is_active);

  // Get exchange rates from stats response
  const exchangeRates = stats?.exchange_rates || {};
  const usdRate = exchangeRates.USD;
  const fx = stats?.fx;
  const rateSummary = [
    usdRate ? `$1 = ${formatINR(usdRate)}` : null,
    exchangeRates.EUR ? `€1 = ${formatINR(exchangeRates.EUR)}` : null,
    exchangeRates.GBP ? `£1 = ${formatINR(exchangeRates.GBP)}` : null,
  ].filter(Boolean).join(' · ');
  const rateWarning = fx?.status === 'unavailable' || fx?.stale;

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Subscriptions</h1>
          <p className="text-white/30 text-[0.8rem]">Track recurring payments and autopay</p>
        </div>
        <GlassButton icon={<Plus size={15} />} onClick={() => setAddOpen(true)}>Add</GlassButton>
      </motion.div>

      {/* Stats Cards */}
      {stats && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-white/90 text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(stats.total_monthly_cost)}</div>
            <div className="text-white/30 text-[0.7rem]">Monthly Cost</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-white/90 text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(stats.total_annual_projection)}</div>
            <div className="text-white/30 text-[0.7rem]">Annual Projection</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-emerald-400/80 text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{stats.active_count}</div>
            <div className="text-white/30 text-[0.7rem]">Active</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-white/40 text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{stats.inactive_count}</div>
            <div className="text-white/30 text-[0.7rem]">Paused</div>
          </div>
        </motion.div>
      )}

      {/* Exchange Rate Banner */}
      {fx && fx.status !== 'not_required' && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.07 }}
          className={`flex items-start gap-2 mb-4 px-4 py-2 rounded-[12px] border ${
            rateWarning
              ? 'bg-amber-400/[0.06] border-amber-400/[0.12]'
              : 'bg-blue-400/[0.06] border-blue-400/[0.1]'
          }`}
        >
          <ArrowRightLeft size={13} className={rateWarning ? 'mt-0.5 text-amber-200/60' : 'mt-0.5 text-blue-400/60'} />
          {fx?.status === 'unavailable' ? (
            <span className="flex-1 text-amber-100/50 text-[0.7rem] leading-relaxed">
              Currency conversion is temporarily unavailable. INR totals are hidden instead of estimated. {fx.unavailable_reason}
            </span>
          ) : (
            <span className={`flex-1 text-[0.7rem] leading-relaxed ${rateWarning ? 'text-amber-100/50' : 'text-white/40'}`}>
              {fx.status === 'stored' ? 'Saved verified rates' : 'Verified reference rates'}{rateSummary && `: ${rateSummary}`}
              {fx?.as_of && <> · As of {fx.as_of}</>}
              {fx?.provider && <> · {fx.provider}</>}
              {fx?.stale && <> · Older rate—refresh when online</>}
            </span>
          )}
          <button
            type="button"
            aria-label="Refresh currency rates"
            onClick={() => rateRefreshMutation.mutate()}
            disabled={rateRefreshMutation.isPending}
            className="min-h-9 shrink-0 rounded-lg border border-white/[0.1] bg-white/[0.04] px-2.5 text-[0.68rem] text-white/45 transition hover:bg-white/[0.08] hover:text-white/70 disabled:opacity-40"
          >
            <RefreshCw size={12} className={`mr-1 inline ${rateRefreshMutation.isPending ? 'animate-spin' : ''}`} />
            Refresh rates
          </button>
        </motion.div>
      )}

      {/* Upcoming reminders */}
      {reminderData?.reminders?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-5 rounded-[18px] bg-amber-400/[0.07] border border-amber-400/[0.14] p-4"
        >
          <div className="flex items-center gap-2 text-amber-200/70 text-xs uppercase tracking-wide">
            <BellRing size={14} /> Due in the next 7 days
          </div>
          <div className="mt-3 grid sm:grid-cols-2 gap-2">
            {reminderData.reminders.map(reminder => (
              <div key={reminder.id} className="min-h-11 flex items-center justify-between gap-3 rounded-xl bg-black/10 px-3 py-2">
                <div>
                  <div className="text-white/60 text-sm">{reminder.name}</div>
                  <div className="text-white/25 text-xs">{reminder.days_until === 0 ? 'Due today' : `Due in ${reminder.days_until} days`}</div>
                </div>
                <div className="text-white/60 text-sm tabular-nums">{formatCurrency(reminder.amount, reminder.currency)}</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Detected subscription confirmations */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider">Detected subscriptions</h2>
          <button
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            className="min-h-11 px-3 rounded-xl text-white/35 hover:text-white/60 hover:bg-white/[0.05] text-xs flex items-center gap-2"
          >
            <RefreshCw size={13} className={scanMutation.isPending ? 'animate-spin' : ''} />
            Detect
          </button>
        </div>
        {suggestions.length === 0 ? (
          <div className="rounded-[16px] bg-white/[0.04] border border-white/[0.09] p-4 text-white/30 text-sm">
            No detected subscriptions need review.
          </div>
        ) : (
          <div className="space-y-2">
            {suggestions.map(suggestion => (
              <div key={suggestion.id} className="rounded-[16px] bg-white/[0.06] border border-white/[0.12] p-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-white/65 text-sm">{suggestion.merchant}</div>
                  <div className="mt-1 text-white/25 text-xs">
                    {formatINR(suggestion.avg_amount)} · {FREQUENCY_LABELS[suggestion.frequency] || suggestion.frequency}
                    {suggestion.next_expected && ` · Expected ${format(new Date(suggestion.next_expected), 'dd MMM')}`}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'confirm' })}
                    className="min-h-11 px-3 rounded-xl bg-emerald-400/10 text-emerald-200/75 border border-emerald-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Check size={13} /> Confirm
                  </button>
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'snooze', snoozeDays: 7 })}
                    className="min-h-11 px-3 rounded-xl bg-amber-400/10 text-amber-200/75 border border-amber-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Clock3 size={13} /> Snooze
                  </button>
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'ignore' })}
                    className="min-h-11 px-3 rounded-xl bg-white/[0.04] text-white/35 border border-white/[0.1] text-xs"
                  >
                    Ignore
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Category Breakdown */}
      {stats?.by_category && Object.keys(stats.by_category).length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5 mb-6"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-3" style={{ fontWeight: 500 }}>By Category (Monthly in INR)</h2>
          <div className="space-y-2">
            {Object.entries(stats.by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, amount]) => {
                const pct = stats.total_monthly_cost > 0 ? (amount / stats.total_monthly_cost) * 100 : 0;
                return (
                  <div key={cat}>
                    <div className="flex justify-between text-[0.8rem] mb-1">
                      <span className="text-white/60">{cat}</span>
                      <span className="text-white/70 tabular-nums">{formatINR(amount)}</span>
                    </div>
                    <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.6, ease: 'easeOut' }}
                        className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-400"
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </motion.div>
      )}

      {/* Active Subscriptions */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="mb-6">
        <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ fontWeight: 500 }}>
          <CreditCard size={14} /> Active ({activeSubs.length})
        </h2>
        {activeSubs.length === 0 ? (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-8 text-center">
            <CreditCard className="h-8 w-8 text-white/20 mx-auto mb-2" />
            <p className="text-sm text-white/40">No active subscriptions. Add one to start tracking.</p>
          </div>
        ) : (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]">
            <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
            <div className="divide-y divide-white/[0.04]">
              {activeSubs.map((sub) => (
                <div key={sub.id} className="flex items-center justify-between px-5 py-3.5 group">
                  <div className="flex-1 min-w-0">
                    <p className="text-white/70 text-[0.85rem]">{sub.name}</p>
                    <p className="text-white/25 text-[0.7rem]">
                      {FREQUENCY_LABELS[sub.frequency] || sub.frequency}
                      {sub.category && ` · ${sub.category}`}
                      {sub.next_payment_date && ` · Next: ${format(new Date(sub.next_payment_date), 'dd MMM')}`}
                    </p>
                  </div>
                  <div className="text-right mr-3">
                    <p className="text-white/70 text-[0.85rem] tabular-nums">
                      {formatCurrency(sub.amount, sub.currency || 'INR')}
                    </p>
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr != null && (
                      <p className="text-white/30 text-[0.65rem] tabular-nums">
                        ≈ {formatINR(sub.amount_inr)}
                      </p>
                    )}
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr == null && (
                      <p className="text-amber-200/35 text-[0.6rem]">INR conversion unavailable</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(sub)}
                      className="text-white/20 hover:text-blue-400/60 transition-colors p-1"
                      title="Edit"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => toggleMutation.mutate({ id: sub.id, is_active: false })}
                      className="text-white/20 hover:text-amber-400/60 transition-colors p-1"
                      title="Pause"
                    >
                      <Pause size={13} />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(sub.id)}
                      className="text-white/20 hover:text-rose-400/60 transition-colors p-1"
                      title="Delete"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </motion.div>

      {/* Inactive/Paused */}
      {inactiveSubs.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-3" style={{ fontWeight: 500 }}>
            Paused ({inactiveSubs.length})
          </h2>
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.05] backdrop-blur-[24px] border border-white/[0.1]">
            <div className="divide-y divide-white/[0.04]">
              {inactiveSubs.map((sub) => (
                <div key={sub.id} className="flex items-center justify-between px-5 py-3 group opacity-60">
                  <div className="flex-1 min-w-0">
                    <p className="text-white/50 text-[0.85rem]">{sub.name}</p>
                    <p className="text-white/20 text-[0.7rem]">{FREQUENCY_LABELS[sub.frequency] || sub.frequency}{sub.category && ` · ${sub.category}`}</p>
                  </div>
                  <div className="text-right mr-3">
                    <p className="text-white/40 text-[0.85rem] tabular-nums">
                      {formatCurrency(sub.amount, sub.currency || 'INR')}
                    </p>
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr != null && (
                      <p className="text-white/25 text-[0.6rem] tabular-nums">≈ {formatINR(sub.amount_inr)}</p>
                    )}
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr == null && (
                      <p className="text-amber-200/30 text-[0.6rem]">INR conversion unavailable</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(sub)}
                      className="text-white/20 hover:text-blue-400/60 transition-colors p-1"
                      title="Edit"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => toggleMutation.mutate({ id: sub.id, is_active: true })}
                      className="text-white/20 hover:text-emerald-400/60 transition-colors p-1"
                      title="Resume"
                    >
                      <Play size={13} />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(sub.id)}
                      className="text-white/20 hover:text-rose-400/60 transition-colors p-1"
                      title="Delete"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* Add Subscription Modal */}
      <AnimatePresence>
        {addOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-md mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-white/90 text-[1.1rem]" style={{ fontWeight: 400 }}>Add Subscription</h3>
                <button onClick={() => setAddOpen(false)} className="text-white/30 hover:text-white/60"><X size={18} /></button>
              </div>
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  createMutation.mutate({
                    name: form.name,
                    amount: parseFloat(form.amount),
                    currency: form.currency,
                    frequency: form.frequency,
                    category: form.category || undefined,
                    subcategory: form.subcategory || undefined,
                    next_payment_date: form.next_payment_date || undefined,
                    notes: form.notes || undefined,
                  });
                }}
              >
                <GlassInput
                  label="Name"
                  placeholder="e.g. Netflix, ChatGPT"
                  value={form.name}
                  onChange={(e) => setForm(p => ({ ...p, name: e.target.value }))}
                  required
                />
                <div className="grid grid-cols-3 gap-3">
                  <GlassInput
                    label="Amount"
                    type="number"
                    placeholder="499"
                    value={form.amount}
                    onChange={(e) => setForm(p => ({ ...p, amount: e.target.value }))}
                    required
                    min={1}
                  />
                  <div>
                    <label className="text-white/40 text-[0.7rem] block mb-1.5">Currency</label>
                    <select
                      value={form.currency}
                      onChange={(e) => setForm(p => ({ ...p, currency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-white/70 outline-none"
                    >
                      {CURRENCIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-white/40 text-[0.7rem] block mb-1.5">Frequency</label>
                    <select
                      value={form.frequency}
                      onChange={(e) => setForm(p => ({ ...p, frequency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-white/70 outline-none"
                    >
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annual">Annual</option>
                    </select>
                  </div>
                </div>
                {/* Live conversion preview */}
                {form.currency !== 'INR' && form.amount && exchangeRates[form.currency] && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-blue-400/[0.06] border border-blue-400/[0.1]">
                    <ArrowRightLeft size={12} className="text-blue-400/50" />
                    <span className="text-white/50 text-[0.75rem]">
                      ≈ {formatINR(parseFloat(form.amount) * exchangeRates[form.currency])} /mo
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <GlassInput
                    label="Category"
                    placeholder="e.g. Entertainment"
                    value={form.category}
                    onChange={(e) => setForm(p => ({ ...p, category: e.target.value }))}
                  />
                  <GlassInput
                    label="Subcategory"
                    placeholder="e.g. Streaming"
                    value={form.subcategory}
                    onChange={(e) => setForm(p => ({ ...p, subcategory: e.target.value }))}
                  />
                </div>
                <GlassInput
                  label="Next Payment Date"
                  type="date"
                  value={form.next_payment_date}
                  onChange={(e) => setForm(p => ({ ...p, next_payment_date: e.target.value }))}
                />
                <GlassInput
                  label="Notes"
                  placeholder="Optional notes"
                  value={form.notes}
                  onChange={(e) => setForm(p => ({ ...p, notes: e.target.value }))}
                />
                <GlassButton type="submit" className="w-full justify-center" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Adding...' : 'Add Subscription'}
                </GlassButton>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Subscription Modal */}
      <AnimatePresence>
        {editSub && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-md mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-white/90 text-[1.1rem]" style={{ fontWeight: 400 }}>Edit Subscription</h3>
                <button onClick={() => setEditSub(null)} className="text-white/30 hover:text-white/60"><X size={18} /></button>
              </div>
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  editMutation.mutate({
                    id: editSub.id,
                    name: editForm.name,
                    amount: parseFloat(editForm.amount),
                    currency: editForm.currency,
                    frequency: editForm.frequency,
                    category: editForm.category || undefined,
                    subcategory: editForm.subcategory || undefined,
                    next_payment_date: editForm.next_payment_date || undefined,
                    notes: editForm.notes || undefined,
                  });
                }}
              >
                <GlassInput
                  label="Name"
                  placeholder="e.g. Netflix, ChatGPT"
                  value={editForm.name}
                  onChange={(e) => setEditForm(p => ({ ...p, name: e.target.value }))}
                  required
                />
                <div className="grid grid-cols-3 gap-3">
                  <GlassInput
                    label="Amount"
                    type="number"
                    placeholder="499"
                    value={editForm.amount}
                    onChange={(e) => setEditForm(p => ({ ...p, amount: e.target.value }))}
                    required
                    min={1}
                  />
                  <div>
                    <label className="text-white/40 text-[0.7rem] block mb-1.5">Currency</label>
                    <select
                      value={editForm.currency}
                      onChange={(e) => setEditForm(p => ({ ...p, currency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-white/70 outline-none"
                    >
                      {CURRENCIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-white/40 text-[0.7rem] block mb-1.5">Frequency</label>
                    <select
                      value={editForm.frequency}
                      onChange={(e) => setEditForm(p => ({ ...p, frequency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-white/70 outline-none"
                    >
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annual">Annual</option>
                    </select>
                  </div>
                </div>
                {editForm.currency !== 'INR' && editForm.amount && exchangeRates[editForm.currency] && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-blue-400/[0.06] border border-blue-400/[0.1]">
                    <ArrowRightLeft size={12} className="text-blue-400/50" />
                    <span className="text-white/50 text-[0.75rem]">
                      ≈ {formatINR(parseFloat(editForm.amount) * exchangeRates[editForm.currency])} /mo
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <GlassInput
                    label="Category"
                    placeholder="e.g. Entertainment"
                    value={editForm.category}
                    onChange={(e) => setEditForm(p => ({ ...p, category: e.target.value }))}
                  />
                  <GlassInput
                    label="Subcategory"
                    placeholder="e.g. Streaming"
                    value={editForm.subcategory}
                    onChange={(e) => setEditForm(p => ({ ...p, subcategory: e.target.value }))}
                  />
                </div>
                <GlassInput
                  label="Next Payment Date"
                  type="date"
                  value={editForm.next_payment_date}
                  onChange={(e) => setEditForm(p => ({ ...p, next_payment_date: e.target.value }))}
                />
                <GlassInput
                  label="Notes"
                  placeholder="Optional notes"
                  value={editForm.notes}
                  onChange={(e) => setEditForm(p => ({ ...p, notes: e.target.value }))}
                />
                <GlassButton type="submit" className="w-full justify-center" disabled={editMutation.isPending}>
                  {editMutation.isPending ? 'Saving...' : 'Save Changes'}
                </GlassButton>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
