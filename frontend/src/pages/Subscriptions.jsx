import { useEffect, useRef, useState } from 'react';
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
  decideSubscriptionSuggestion, fetchSubscriptionReminders, fetchExchangeRates,
  fetchRecurringCandidates, refreshExchangeRates, restoreSubscription,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import { useToast } from '../context/ToastContext';
import DialogSurface from '../components/DialogSurface';
import { useConfirm } from '../components/ConfirmDialog';

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
  const [scanSummary, setScanSummary] = useState(null);
  const [recentDeletion, setRecentDeletion] = useState(null);
  const undoRef = useRef(null);
  const { confirm, ConfirmDialog: ConfirmDialogComponent } = useConfirm();
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

  const { data: recurringCandidates = [] } = useQuery({
    queryKey: ['recurringCandidates'],
    queryFn: fetchRecurringCandidates,
  });

  const { data: fxReference, isLoading: fxLoading } = useQuery({
    queryKey: ['referenceFx'],
    queryFn: fetchExchangeRates,
  });

  const { data: reminderData } = useQuery({
    queryKey: ['subscriptionReminders'],
    queryFn: () => fetchSubscriptionReminders(7),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    queryClient.invalidateQueries({ queryKey: ['subscriptionStats'] });
    queryClient.invalidateQueries({ queryKey: ['subscriptionReminders'] });
    queryClient.invalidateQueries({ queryKey: ['referenceFx'] });
  };

  const scanMutation = useMutation({
    mutationFn: scanSubscriptionSuggestions,
    onSuccess: (result) => {
      setScanSummary(result);
      queryClient.invalidateQueries({ queryKey: ['subscriptionSuggestions'] });
      queryClient.invalidateQueries({ queryKey: ['recurringCandidates'] });
      if (result.created_suggestions > 0) {
        showToast(`Found ${result.created_suggestions} subscription${result.created_suggestions === 1 ? '' : 's'} for you to review.`);
      } else if (result.candidate_patterns > 0) {
        showToast(`Found ${result.candidate_patterns} possible recurring payment${result.candidate_patterns === 1 ? '' : 's'} that need more evidence.`, 'info');
      } else {
        showToast(`No recurring pattern found in ${result.transactions_considered} eligible transaction${result.transactions_considered === 1 ? '' : 's'}.`, 'info');
      }
    },
  });

  const rateRefreshMutation = useMutation({
    mutationFn: refreshExchangeRates,
    onSuccess: (result) => {
      invalidate();
      if (result?.fx?.status === 'unavailable') {
        showToast('Live reference rates are unavailable, so GODFIN did not estimate them.', 'error');
      } else if (result?.fx?.status === 'stored' || result?.fx?.status === 'stale') {
        showToast('Could not reach the rate provider. The last verified reference rates are still shown.', 'info');
      } else {
        showToast('Reference rates refreshed and saved on this computer.');
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
    mutationFn: sub => deleteSubscription(sub.id).then(result => ({ ...result, sub })),
    onSuccess: result => {
      invalidate();
      setRecentDeletion(result);
      showToast('Subscription removed. You can undo this change.', 'info');
    },
  });

  const restoreMutation = useMutation({
    mutationFn: restoreSubscription,
    onSuccess: () => {
      invalidate();
      setRecentDeletion(null);
      showToast('Subscription restored.', 'success');
    },
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

  useEffect(() => {
    if (recentDeletion) undoRef.current?.focus();
  }, [recentDeletion]);

  const requestDelete = async (sub) => {
    const confirmed = await confirm({
      title: `Remove ${sub.name}?`,
      message: 'This will hide 1 subscription from reminders and totals. You can undo it; the local record is not erased.',
      confirmLabel: 'Remove subscription',
      cancelLabel: 'Keep subscription',
      danger: true,
    });
    if (confirmed) deleteMutation.mutate(sub);
  };

  const activeSubs = subs.filter(s => s.is_active);
  const inactiveSubs = subs.filter(s => !s.is_active);

  const exchangeRates = fxReference?.rates || {};
  const usdRate = exchangeRates.USD;
  const fx = fxReference?.fx;
  const rateSummary = [
    usdRate ? `$1 = ${formatINR(usdRate)}` : null,
    exchangeRates.EUR ? `€1 = ${formatINR(exchangeRates.EUR)}` : null,
    exchangeRates.GBP ? `£1 = ${formatINR(exchangeRates.GBP)}` : null,
  ].filter(Boolean).join(' · ');
  const rateWarning = !fx || fx?.status === 'unavailable' || fx?.stale;

  const addCandidate = (candidate) => {
    setForm({
      name: candidate.merchant,
      amount: String(candidate.avg_amount),
      currency: 'INR',
      frequency: candidate.frequency,
      category: candidate.category || '',
      subcategory: '',
      next_payment_date: candidate.next_expected || '',
      notes: `Possible recurring payment based on ${candidate.evidence_count} transactions.`,
    });
    setAddOpen(true);
  };

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-ink-primary text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Subscriptions</h1>
          <p className="text-ink-muted text-[0.8rem]">Track recurring payments and autopay</p>
        </div>
        <GlassButton icon={<Plus size={15} />} onClick={() => setAddOpen(true)}>Add</GlassButton>
      </motion.div>

      {recentDeletion && (
        <div role="status" className="mb-5 flex flex-wrap items-center gap-3 rounded-[14px] border border-amber-300/20 bg-amber-300/[0.07] px-4 py-3 text-sm text-amber-50">
          <span className="flex-1">Removed {recentDeletion.sub.name}. The local record can be recovered.</span>
          <button
            ref={undoRef}
            type="button"
            onClick={() => restoreMutation.mutate(recentDeletion.id)}
            disabled={restoreMutation.isPending}
            className="min-h-10 rounded-lg border border-amber-200/25 px-3 text-amber-50 hover:bg-amber-200/[0.08] disabled:opacity-40"
          >
            {restoreMutation.isPending ? 'Restoring…' : 'Undo'}
          </button>
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-ink-primary text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(stats.total_monthly_cost)}</div>
            <div className="text-ink-muted text-[0.7rem]">Monthly Cost</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-ink-primary text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(stats.total_annual_projection)}</div>
            <div className="text-ink-muted text-[0.7rem]">Annual Projection</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-emerald-200 text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{stats.active_count}</div>
            <div className="text-ink-muted text-[0.7rem]">Active</div>
          </div>
          <div className="relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-4">
            <div className="text-ink-muted text-[1.3rem] tabular-nums" style={{ fontWeight: 300 }}>{stats.inactive_count}</div>
            <div className="text-ink-muted text-[0.7rem]">Paused</div>
          </div>
        </motion.div>
      )}

      {/* Reference rates are useful even before a foreign subscription exists. */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.07 }}
        className={`mb-4 rounded-[16px] border px-4 py-3 ${
          rateWarning
            ? 'bg-amber-400/[0.06] border-amber-400/[0.12]'
            : 'bg-blue-400/[0.06] border-blue-400/[0.1]'
        }`}
      >
        <div className="flex items-start gap-3">
          <ArrowRightLeft size={14} className={rateWarning ? 'mt-0.5 text-amber-200' : 'mt-0.5 text-blue-200'} />
          <div className="min-w-0 flex-1">
            <div className="text-[0.72rem] font-medium uppercase tracking-wider text-ink-secondary">Reference FX</div>
            {fxLoading ? (
              <p className="mt-1 text-[0.7rem] text-ink-muted">Checking verified USD, EUR, and GBP reference rates…</p>
            ) : fx?.status === 'unavailable' || !fx ? (
              <p className="mt-1 text-[0.7rem] leading-relaxed text-amber-100">
                Currency reference rates are temporarily unavailable. GODFIN hides converted totals instead of guessing.
              </p>
            ) : (
              <>
                <p className={`mt-1 text-[0.72rem] leading-relaxed ${rateWarning ? 'text-amber-100' : 'text-ink-muted'}`}>
                  {rateSummary || 'No reference rates returned'}
                </p>
                <p className="mt-1 text-[0.64rem] leading-relaxed text-ink-muted">
                  {fx.status === 'stored' ? 'Last verified and saved on this computer' : fx.status === 'stale' ? 'Saved rate is older—refresh when online' : 'Live verified reference'}
                  {fx.as_of && ` · As of ${fx.as_of}`}
                  {fx.provider && ` · ${fx.provider}`}
                </p>
              </>
            )}
            <p className="mt-1 text-[0.62rem] text-ink-muted">Only currency codes are sent to the public rate provider; no financial records leave GODFIN.</p>
          </div>
          <button
            type="button"
            aria-label="Refresh reference currency rates"
            onClick={() => rateRefreshMutation.mutate()}
            disabled={rateRefreshMutation.isPending}
            className="min-h-9 shrink-0 rounded-lg border border-white/[0.1] bg-white/[0.04] px-2.5 text-[0.68rem] text-ink-muted transition hover:bg-white/[0.08] hover:text-ink-secondary disabled:opacity-40"
          >
            <RefreshCw size={12} className={`mr-1 inline ${rateRefreshMutation.isPending ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </motion.div>

      {/* Upcoming reminders */}
      {reminderData?.reminders?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-5 rounded-[18px] bg-amber-400/[0.07] border border-amber-400/[0.14] p-4"
        >
          <div className="flex items-center gap-2 text-amber-200 text-xs uppercase tracking-wide">
            <BellRing size={14} /> Due in the next 7 days
          </div>
          <div className="mt-3 grid sm:grid-cols-2 gap-2">
            {reminderData.reminders.map(reminder => (
              <div key={reminder.id} className="min-h-11 flex items-center justify-between gap-3 rounded-xl bg-black/10 px-3 py-2">
                <div>
                  <div className="text-ink-secondary text-sm">{reminder.name}</div>
                  <div className="text-ink-muted text-xs">{reminder.days_until === 0 ? 'Due today' : `Due in ${reminder.days_until} days`}</div>
                </div>
                <div className="text-ink-secondary text-sm tabular-nums">{formatCurrency(reminder.amount, reminder.currency)}</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Detected subscription confirmations */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider">Detected subscriptions</h2>
          <button
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            className="min-h-11 px-3 rounded-xl text-ink-muted hover:text-ink-secondary hover:bg-white/[0.05] text-xs flex items-center gap-2"
          >
            <RefreshCw size={13} className={scanMutation.isPending ? 'animate-spin' : ''} />
            Detect
          </button>
        </div>
        {scanSummary && (
          <div role="status" className="mb-3 rounded-[14px] border border-cyan-300/10 bg-cyan-300/[0.04] px-4 py-3 text-xs leading-relaxed text-ink-muted">
            Checked {scanSummary.transactions_considered} eligible transaction{scanSummary.transactions_considered === 1 ? '' : 's'} across {scanSummary.merchant_groups_scanned} merchant group{scanSummary.merchant_groups_scanned === 1 ? '' : 's'}.{' '}
            {scanSummary.created_suggestions > 0
              ? `${scanSummary.created_suggestions} new subscription review ${scanSummary.created_suggestions === 1 ? 'item was' : 'items were'} created.`
              : scanSummary.candidate_patterns > 0
                ? `${scanSummary.candidate_patterns} possible recurring ${scanSummary.candidate_patterns === 1 ? 'payment needs' : 'payments need'} more evidence.`
                : 'No supported recurring payment pattern was found.'}
            {(scanSummary.excluded_non_spend > 0 || scanSummary.insufficient_evidence > 0) && (
              <> {scanSummary.excluded_non_spend} non-spend row{scanSummary.excluded_non_spend === 1 ? ' was' : 's were'} excluded; {scanSummary.insufficient_evidence} group{scanSummary.insufficient_evidence === 1 ? ' had' : 's had'} too little evidence.</>
            )}
          </div>
        )}
        {suggestions.length === 0 ? (
          <div className="rounded-[16px] bg-white/[0.04] border border-white/[0.09] p-4 text-ink-muted text-sm">
            No detected subscriptions need review.
          </div>
        ) : (
          <div className="space-y-2">
            {suggestions.map(suggestion => (
              <div key={suggestion.id} className="rounded-[16px] bg-white/[0.06] border border-white/[0.12] p-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-ink-secondary text-sm">{suggestion.merchant}</div>
                  <div className="mt-1 text-ink-muted text-xs">
                    {formatINR(suggestion.avg_amount)} · {FREQUENCY_LABELS[suggestion.frequency] || suggestion.frequency}
                    {suggestion.next_expected && ` · Expected ${format(new Date(suggestion.next_expected), 'dd MMM')}`}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'confirm' })}
                    className="min-h-11 px-3 rounded-xl bg-emerald-400/10 text-emerald-200 border border-emerald-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Check size={13} /> Confirm
                  </button>
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'snooze', snoozeDays: 7 })}
                    className="min-h-11 px-3 rounded-xl bg-amber-400/10 text-amber-200 border border-amber-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Clock3 size={13} /> Snooze
                  </button>
                  <button
                    onClick={() => suggestionMutation.mutate({ id: suggestion.id, decision: 'ignore' })}
                    className="min-h-11 px-3 rounded-xl bg-white/[0.04] text-ink-muted border border-white/[0.1] text-xs"
                  >
                    Ignore
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {recurringCandidates.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
          <h2 className="mb-3 text-[0.7rem] uppercase tracking-wider text-ink-muted">Possible recurring payments</h2>
          <p className="mb-3 text-xs leading-relaxed text-ink-muted">These look regular but do not yet have enough evidence to become subscriptions automatically. Nothing is added unless you choose it.</p>
          <div className="space-y-2">
            {recurringCandidates.map(candidate => (
              <div key={candidate.id} className="flex flex-wrap items-center justify-between gap-3 rounded-[16px] border border-amber-300/[0.12] bg-amber-300/[0.04] p-4">
                <div>
                  <div className="text-sm text-ink-secondary">{candidate.merchant}</div>
                  <div className="mt-1 text-xs text-ink-muted">
                    {formatINR(candidate.avg_amount)} · {FREQUENCY_LABELS[candidate.frequency] || candidate.frequency} · {candidate.evidence_count} payments · {candidate.amount_behavior} amount
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => addCandidate(candidate)}
                  className="min-h-11 rounded-xl border border-amber-200/20 bg-amber-200/[0.06] px-3 text-xs text-amber-100 hover:bg-amber-200/[0.1]"
                >
                  Add manually
                </button>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Category Breakdown */}
      {stats?.by_category && Object.keys(stats.by_category).length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5 mb-6"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider mb-3" style={{ fontWeight: 500 }}>By Category (Monthly in INR)</h2>
          <div className="space-y-2">
            {Object.entries(stats.by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, amount]) => {
                const pct = stats.total_monthly_cost > 0 ? (amount / stats.total_monthly_cost) * 100 : 0;
                return (
                  <div key={cat}>
                    <div className="flex justify-between text-[0.8rem] mb-1">
                      <span className="text-ink-secondary">{cat}</span>
                      <span className="text-ink-secondary tabular-nums">{formatINR(amount)}</span>
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
        <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ fontWeight: 500 }}>
          <CreditCard size={14} /> Active ({activeSubs.length})
        </h2>
        {activeSubs.length === 0 ? (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] p-8 text-center">
            <CreditCard className="h-8 w-8 text-ink-muted mx-auto mb-2" />
            <p className="text-sm text-ink-muted">No active subscriptions. Add one to start tracking.</p>
          </div>
        ) : (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]">
            <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
            <div className="divide-y divide-white/[0.04]">
              {activeSubs.map((sub) => (
                <div key={sub.id} className="flex items-center justify-between px-5 py-3.5 group">
                  <div className="flex-1 min-w-0">
                    <p className="text-ink-secondary text-[0.85rem]">{sub.name}</p>
                    <p className="text-ink-muted text-[0.7rem]">
                      {FREQUENCY_LABELS[sub.frequency] || sub.frequency}
                      {sub.category && ` · ${sub.category}`}
                      {sub.next_payment_date && ` · Next: ${format(new Date(sub.next_payment_date), 'dd MMM')}`}
                    </p>
                  </div>
                  <div className="text-right mr-3">
                    <p className="text-ink-secondary text-[0.85rem] tabular-nums">
                      {formatCurrency(sub.amount, sub.currency || 'INR')}
                    </p>
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr != null && (
                      <p className="text-ink-muted text-[0.65rem] tabular-nums">
                        ≈ {formatINR(sub.amount_inr)}
                      </p>
                    )}
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr == null && (
                      <p className="text-amber-200 text-[0.6rem]">INR conversion unavailable</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(sub)}
                      className="text-ink-muted hover:text-blue-200 transition-colors p-1"
                      title="Edit"
                      aria-label={`Edit subscription ${sub.name}`}
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => toggleMutation.mutate({ id: sub.id, is_active: false })}
                      className="text-ink-muted hover:text-amber-200 transition-colors p-1"
                      title="Pause"
                      aria-label={`Pause subscription ${sub.name}`}
                    >
                      <Pause size={13} />
                    </button>
                    <button
                      onClick={() => requestDelete(sub)}
                      disabled={deleteMutation.isPending}
                      className="text-ink-muted hover:text-rose-200 transition-colors p-1"
                      title="Delete"
                      aria-label={`Delete subscription ${sub.name}`}
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
          <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider mb-3" style={{ fontWeight: 500 }}>
            Paused ({inactiveSubs.length})
          </h2>
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.05] backdrop-blur-[24px] border border-white/[0.1]">
            <div className="divide-y divide-white/[0.04]">
              {inactiveSubs.map((sub) => (
                <div key={sub.id} className="flex items-center justify-between px-5 py-3 group opacity-60">
                  <div className="flex-1 min-w-0">
                    <p className="text-ink-muted text-[0.85rem]">{sub.name}</p>
                    <p className="text-ink-muted text-[0.7rem]">{FREQUENCY_LABELS[sub.frequency] || sub.frequency}{sub.category && ` · ${sub.category}`}</p>
                  </div>
                  <div className="text-right mr-3">
                    <p className="text-ink-muted text-[0.85rem] tabular-nums">
                      {formatCurrency(sub.amount, sub.currency || 'INR')}
                    </p>
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr != null && (
                      <p className="text-ink-muted text-[0.6rem] tabular-nums">≈ {formatINR(sub.amount_inr)}</p>
                    )}
                    {sub.currency && sub.currency !== 'INR' && sub.amount_inr == null && (
                      <p className="text-amber-200 text-[0.6rem]">INR conversion unavailable</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(sub)}
                      className="text-ink-muted hover:text-blue-200 transition-colors p-1"
                      title="Edit"
                      aria-label={`Edit subscription ${sub.name}`}
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => toggleMutation.mutate({ id: sub.id, is_active: true })}
                      className="text-ink-muted hover:text-emerald-200 transition-colors p-1"
                      title="Resume"
                      aria-label={`Resume subscription ${sub.name}`}
                    >
                      <Play size={13} />
                    </button>
                    <button
                      onClick={() => requestDelete(sub)}
                      disabled={deleteMutation.isPending}
                      className="text-ink-muted hover:text-rose-200 transition-colors p-1"
                      title="Delete"
                      aria-label={`Delete subscription ${sub.name}`}
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
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" role="presentation">
            <DialogSurface
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              labelledBy="add-subscription-title"
              onClose={() => setAddOpen(false)}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-md mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-5">
                <h3 id="add-subscription-title" className="text-ink-primary text-[1.1rem]" style={{ fontWeight: 400 }}>Add Subscription</h3>
                <button onClick={() => setAddOpen(false)} className="text-ink-muted hover:text-ink-secondary" aria-label="Close add subscription dialog"><X size={18} /></button>
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
                    <label htmlFor="add-subscription-currency" className="text-ink-muted text-[0.7rem] block mb-1.5">Currency</label>
                    <select
                      id="add-subscription-currency"
                      value={form.currency}
                      onChange={(e) => setForm(p => ({ ...p, currency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-ink-secondary outline-none"
                    >
                      {CURRENCIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="add-subscription-frequency" className="text-ink-muted text-[0.7rem] block mb-1.5">Frequency</label>
                    <select
                      id="add-subscription-frequency"
                      value={form.frequency}
                      onChange={(e) => setForm(p => ({ ...p, frequency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-ink-secondary outline-none"
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
                    <ArrowRightLeft size={12} className="text-blue-200" />
                    <span className="text-ink-muted text-[0.75rem]">
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
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Subscription Modal */}
      <AnimatePresence>
        {editSub && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" role="presentation">
            <DialogSurface
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              labelledBy="edit-subscription-title"
              onClose={() => setEditSub(null)}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-md mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-5">
                <h3 id="edit-subscription-title" className="text-ink-primary text-[1.1rem]" style={{ fontWeight: 400 }}>Edit Subscription</h3>
                <button onClick={() => setEditSub(null)} className="text-ink-muted hover:text-ink-secondary" aria-label="Close edit subscription dialog"><X size={18} /></button>
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
                    <label htmlFor="edit-subscription-currency" className="text-ink-muted text-[0.7rem] block mb-1.5">Currency</label>
                    <select
                      id="edit-subscription-currency"
                      value={editForm.currency}
                      onChange={(e) => setEditForm(p => ({ ...p, currency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-ink-secondary outline-none"
                    >
                      {CURRENCIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="edit-subscription-frequency" className="text-ink-muted text-[0.7rem] block mb-1.5">Frequency</label>
                    <select
                      id="edit-subscription-frequency"
                      value={editForm.frequency}
                      onChange={(e) => setEditForm(p => ({ ...p, frequency: e.target.value }))}
                      className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] px-3 py-2.5 text-[0.85rem] text-ink-secondary outline-none"
                    >
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annual">Annual</option>
                    </select>
                  </div>
                </div>
                {editForm.currency !== 'INR' && editForm.amount && exchangeRates[editForm.currency] && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-[10px] bg-blue-400/[0.06] border border-blue-400/[0.1]">
                    <ArrowRightLeft size={12} className="text-blue-200" />
                    <span className="text-ink-muted text-[0.75rem]">
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
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>
      <ConfirmDialogComponent />
    </div>
  );
}
