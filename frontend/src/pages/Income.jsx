import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, DollarSign, TrendingUp, Calendar, Trash2, X, Check, Edit2, AlertCircle,
  Search, Loader2,
} from 'lucide-react';
import { format } from 'date-fns';
import {
  fetchIncomeSources, createIncomeSource, updateIncomeSource, deleteIncomeSource, fetchIncomeStats,
  fetchIncomeCoverage, fetchAccounts, scanIncomeMatches, fetchIncomeMatches,
  confirmIncomeMatches, dismissIncomeMatches,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import { StatCard } from '../components/StatCard';
import { useConfirm } from '../components/ConfirmDialog';
import DialogSurface from '../components/DialogSurface';

function formatINR(amount) {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

const frequencyColors = {
  monthly: 'bg-emerald-400/[0.1] text-emerald-400/70 border border-emerald-400/[0.12]',
  quarterly: 'bg-blue-400/[0.1] text-blue-400/70 border border-blue-400/[0.12]',
  annual: 'bg-violet-400/[0.1] text-violet-400/70 border border-violet-400/[0.12]',
  one_time: 'bg-white/[0.06] text-white/40 border border-white/[0.08]',
};

function AddIncomeModal({ open, onClose, editSource = null, coverage, accounts, onFindPast }) {
  const [sourceName, setSourceName] = useState(editSource?.source_name || '');
  const [expectedAmount, setExpectedAmount] = useState(editSource?.expected_amount ?? '');
  const [frequency, setFrequency] = useState(editSource?.frequency || 'monthly');
  const [nextExpectedDate, setNextExpectedDate] = useState(editSource?.next_expected_date || '');
  const [effectiveFrom, setEffectiveFrom] = useState(
    editSource?.effective_from
      || coverage?.earliest_transaction_date
      || new Date().toISOString().split('T')[0],
  );
  const [effectiveTo, setEffectiveTo] = useState(editSource?.effective_to || '');
  const [tolerancePercent, setTolerancePercent] = useState(
    String(Math.round((editSource?.amount_tolerance ?? 0.2) * 100)),
  );
  const [payerAlias, setPayerAlias] = useState(editSource?.confirmed_merchant_alias || '');
  const [accountId, setAccountId] = useState(editSource?.account_id || '');
  const [paymentRail, setPaymentRail] = useState(editSource?.payment_rail || '');
  const [findPast, setFindPast] = useState(!editSource);
  const [error, setError] = useState('');
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (data) => createIncomeSource(data),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
      queryClient.invalidateQueries({ queryKey: ['incomeStats'] });
      onClose();
      if (findPast) onFindPast(created);
    },
    onError: (err) => setError(err.message || 'Failed to create income source'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => updateIncomeSource(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
      queryClient.invalidateQueries({ queryKey: ['incomeStats'] });
      onClose();
    },
    onError: (err) => setError(err.message || 'Failed to update income source'),
  });

  const handleFrequencyChange = (newFreq) => {
    setFrequency(newFreq);
    if (newFreq !== 'one_time' && !nextExpectedDate && expectedAmount) {
      const today = new Date();
      let defaultDate;
      if (newFreq === 'monthly') {
        defaultDate = new Date(today.getFullYear(), today.getMonth() + 1, 1);
      } else if (newFreq === 'quarterly') {
        const currentQuarter = Math.floor(today.getMonth() / 3);
        const nextQuarterMonth = (currentQuarter + 1) * 3;
        defaultDate = new Date(today.getFullYear(), nextQuarterMonth, 1);
      } else if (newFreq === 'annual') {
        defaultDate = new Date(today.getFullYear() + 1, 0, 1);
      }
      if (defaultDate) {
        setNextExpectedDate(defaultDate.toISOString().split('T')[0]);
      }
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');
    if (!sourceName.trim()) {
      setError('Please enter a source name');
      return;
    }
    if (!effectiveFrom) {
      setError('Choose when this income source started');
      return;
    }
    if (effectiveTo && effectiveTo < effectiveFrom) {
      setError('The end date cannot be before the start date');
      return;
    }
    const tolerance = Number(tolerancePercent);
    if (!Number.isFinite(tolerance) || tolerance < 0 || tolerance > 100) {
      setError('Amount variation must be between 0% and 100%');
      return;
    }
    const data = {
      source_name: sourceName.trim(),
      expected_amount: expectedAmount ? parseFloat(expectedAmount) : null,
      frequency,
      next_expected_date: nextExpectedDate || null,
      enforce_current_month: false,
      effective_from: effectiveFrom,
      effective_to: effectiveTo || null,
      amount_tolerance: tolerance / 100,
      confirmed_merchant_alias: payerAlias.trim() || null,
      account_id: accountId || null,
      payment_rail: paymentRail || null,
    };
    if (editSource) {
      updateMutation.mutate({ id: editSource.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" role="presentation">
      <DialogSurface
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        labelledBy="income-modal-title"
        onClose={onClose}
        className="relative overflow-y-auto max-h-[90vh] rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-lg mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
      >
        <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
        <div className="flex items-center justify-between mb-5">
          <h3 id="income-modal-title" className="text-white/90 text-[1.1rem]" style={{ fontWeight: 400 }}>
            {editSource ? 'Edit Income Source' : 'Add Income Source'}
          </h3>
          <button onClick={onClose} className="text-white/30 hover:text-white/60" aria-label="Close modal"><X size={18} /></button>
        </div>
        {error && (
          <div className="mb-4 p-3 bg-rose-400/[0.08] border border-rose-400/[0.15] rounded-[12px] flex items-center gap-2 text-rose-400/80 text-[0.8rem]" role="alert">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <GlassInput
            label="Source Name"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            placeholder="e.g., Salary, Freelance, Dividends"
            required
          />
          <GlassInput
            label="Expected Amount (₹)"
            type="number"
            value={expectedAmount}
            onChange={(e) => setExpectedAmount(e.target.value)}
            placeholder="e.g., 50000"
            min="0.01"
            step="0.01"
          />
          <div>
            <label htmlFor="income-frequency" className="block text-white/40 text-[0.75rem] mb-1.5" style={{ fontWeight: 400 }}>Frequency</label>
            <select
              id="income-frequency"
              value={frequency}
              onChange={(e) => handleFrequencyChange(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.12] rounded-[14px] text-white/80 text-[0.85rem] focus:outline-none focus:border-cyan-400/30"
            >
              <option value="monthly" className="bg-[#1a2a4a]">Monthly</option>
              <option value="quarterly" className="bg-[#1a2a4a]">Quarterly</option>
              <option value="annual" className="bg-[#1a2a4a]">Annual</option>
              <option value="one_time" className="bg-[#1a2a4a]">One Time</option>
            </select>
          </div>
          {frequency !== 'one_time' && (
            <GlassInput
              label="Next Expected Date (optional)"
              type="date"
              value={nextExpectedDate}
              onChange={(e) => setNextExpectedDate(e.target.value)}
            />
          )}
          <div className="grid grid-cols-2 gap-3">
            <GlassInput
              label="Started on"
              type="date"
              value={effectiveFrom}
              min={coverage?.earliest_transaction_date || undefined}
              onChange={(e) => setEffectiveFrom(e.target.value)}
              required
            />
            <GlassInput
              label="Ended on (optional)"
              type="date"
              value={effectiveTo}
              min={effectiveFrom || undefined}
              onChange={(e) => setEffectiveTo(e.target.value)}
            />
          </div>
          <p className="text-white/30 text-[0.7rem] -mt-2">
            GODFIN only expects this income inside these dates. It never creates missing income automatically.
          </p>
          <GlassInput
            label="Usual amount variation (%)"
            type="number"
            value={tolerancePercent}
            onChange={(e) => setTolerancePercent(e.target.value)}
            min="0"
            max="100"
            step="1"
          />
          <GlassInput
            label="Payer name seen in your statement (optional)"
            value={payerAlias}
            onChange={(e) => setPayerAlias(e.target.value)}
            placeholder="e.g., ACME PAYROLL"
          />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="income-account" className="block text-white/40 text-[0.75rem] mb-1.5">Account (optional)</label>
              <select
                id="income-account"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-white/80 text-[0.85rem]"
              >
                <option value="" className="bg-[#1a2a4a]">Any account</option>
                {(accounts || []).map((account) => (
                  <option key={account.id} value={account.id} className="bg-[#1a2a4a]">
                    {account.nickname || account.bank} · {account.last_4_digits}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="income-payment-rail" className="block text-white/40 text-[0.75rem] mb-1.5">Paid through (optional)</label>
              <select
                id="income-payment-rail"
                value={paymentRail}
                onChange={(e) => setPaymentRail(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-white/80 text-[0.85rem]"
              >
                <option value="" className="bg-[#1a2a4a]">Any method</option>
                <option value="bank" className="bg-[#1a2a4a]">Bank transfer</option>
                <option value="upi" className="bg-[#1a2a4a]">UPI</option>
                <option value="cheque" className="bg-[#1a2a4a]">Cheque</option>
                <option value="cash" className="bg-[#1a2a4a]">Cash</option>
                <option value="other" className="bg-[#1a2a4a]">Other</option>
              </select>
            </div>
          </div>
          {!editSource && (
            <div className="flex items-start gap-3 p-3 bg-cyan-400/[0.05] rounded-[12px] border border-cyan-400/[0.1]">
              <input
                type="checkbox"
                id="findPastIncome"
                checked={findPast}
                onChange={(e) => setFindPast(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-white/[0.2] bg-white/[0.05] text-cyan-400"
              />
              <div>
                <label htmlFor="findPastIncome" className="text-white/70 text-[0.85rem] cursor-pointer">Find past matching income after saving</label>
                <p className="text-white/30 text-[0.7rem] mt-0.5">You review every suggested credit before GODFIN changes anything.</p>
              </div>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <GlassButton variant="secondary" onClick={onClose} className="flex-1 justify-center">Cancel</GlassButton>
            <GlassButton type="submit" disabled={isLoading} className="flex-1 justify-center">
              {isLoading ? 'Saving...' : editSource ? 'Update' : 'Add Source'}
            </GlassButton>
          </div>
        </form>
      </DialogSurface>
    </div>
  );
}


function IncomeMatchReview({ source, onClose }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(null);
  const [subcategory, setSubcategory] = useState(
    source?.source_name?.toLowerCase().includes('salary') ? 'Salary' : 'Other Income',
  );

  const { data: matches, isLoading: matchesLoading } = useQuery({
    queryKey: ['incomeMatches', source?.id, 'pending'],
    queryFn: () => fetchIncomeMatches(source.id),
    enabled: Boolean(source?.id),
  });
  const scanMutation = useMutation({
    mutationFn: () => scanIncomeMatches(source.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incomeMatches', source.id] }),
  });
  const { mutate: runScan } = scanMutation;

  useEffect(() => {
    if (source?.id) runScan();
  }, [source?.id, runScan]);

  const refreshFinancialViews = () => {
    queryClient.invalidateQueries({ queryKey: ['incomeMatches', source.id] });
    queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
    queryClient.invalidateQueries({ queryKey: ['incomeStats'] });
    queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
    queryClient.invalidateQueries({ queryKey: ['cashFlow'] });
    queryClient.invalidateQueries({ queryKey: ['report'] });
  };
  const strongIds = (matches?.items || [])
    .filter((item) => item.strength === 'strong')
    .map((item) => item.id);
  const selectedIds = selected ?? strongIds;
  const confirmMutation = useMutation({
    mutationFn: () => confirmIncomeMatches(source.id, selectedIds, subcategory),
    onSuccess: () => {
      setSelected([]);
      refreshFinancialViews();
    },
  });
  const dismissMutation = useMutation({
    mutationFn: () => dismissIncomeMatches(source.id, selectedIds),
    onSuccess: () => {
      setSelected([]);
      refreshFinancialViews();
    },
  });

  const items = matches?.items || [];
  const busy = scanMutation.isPending || confirmMutation.isPending || dismissMutation.isPending;
  const error = scanMutation.error || confirmMutation.error || dismissMutation.error;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="presentation">
      <DialogSurface
        labelledBy="income-match-title"
        onClose={onClose}
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto mx-4 rounded-[24px] bg-[#0d2040]/95 border border-white/[0.15] p-6 shadow-[0_16px_64px_rgba(0,0,0,0.35)]"
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 id="income-match-title" className="text-white/90 text-lg">Review past income</h3>
            <p className="text-white/35 text-xs mt-1">
              {source.source_name} · {source.effective_from} onward. Nothing changes until you confirm it.
            </p>
          </div>
          <button onClick={onClose} className="p-2 text-white/40 hover:text-white/70" aria-label="Close past income review">
            <X size={18} />
          </button>
        </div>

        {scanMutation.data && (
          <div className="mb-4 rounded-[14px] border border-cyan-400/[0.12] bg-cyan-400/[0.05] p-3 text-xs text-white/50">
            Checked {scanMutation.data.scanned} credits from {scanMutation.data.coverage_start} to {scanMutation.data.coverage_end}. Found {scanMutation.data.strong} strong and {scanMutation.data.uncertain} uncertain match{scanMutation.data.uncertain === 1 ? '' : 'es'}. Safely excluded {scanMutation.data.excluded_unsafe} refund, transfer, reversal, or locked credit{scanMutation.data.excluded_unsafe === 1 ? '' : 's'}.
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-[12px] border border-rose-400/20 bg-rose-400/[0.08] p-3 text-sm text-rose-300" role="alert">
            {error.message || 'GODFIN could not finish the income review.'}
          </div>
        )}

        {matchesLoading || scanMutation.isPending ? (
          <div className="py-12 flex items-center justify-center gap-2 text-white/40 text-sm">
            <Loader2 size={18} className="animate-spin" /> Checking your local transactions…
          </div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center">
            <Check className="mx-auto text-emerald-400/60 mb-2" size={26} />
            <p className="text-white/60">No unreviewed matches</p>
            <p className="text-white/30 text-xs mt-1">GODFIN did not guess from amount alone.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <label key={item.id} className="flex gap-3 rounded-[14px] border border-white/[0.08] bg-white/[0.04] p-3 cursor-pointer hover:bg-white/[0.06]">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(item.id)}
                  onChange={(event) => setSelected((current) => (
                    event.target.checked
                      ? [...(current ?? selectedIds), item.id]
                      : (current ?? selectedIds).filter((id) => id !== item.id)
                  ))}
                  className="mt-1 h-4 w-4 rounded border-white/20 bg-white/5 text-cyan-400"
                  aria-label={`Select ${item.merchant} credit from ${item.date}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-white/75 text-sm">{item.merchant}</span>
                    <span className="text-white/80 tabular-nums text-sm">{formatINR(item.amount)}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[0.68rem] text-white/35">
                    <span>{item.date}</span><span>·</span><span>{item.instrument}</span>
                    <span className={item.strength === 'strong' ? 'text-emerald-300/70' : 'text-amber-300/70'}>
                      {item.strength === 'strong' ? 'Strong match' : 'Needs a closer look'}
                    </span>
                  </div>
                  <ul className="mt-1 text-[0.68rem] text-white/30 list-disc list-inside">
                    {item.evidence.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                </div>
              </label>
            ))}
          </div>
        )}

        {items.length > 0 && (
          <div className="mt-5 border-t border-white/[0.08] pt-4 flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="flex-1">
              <label htmlFor="income-match-kind" className="block text-white/40 text-xs mb-1.5">What kind of income is this?</label>
              <select
                id="income-match-kind"
                value={subcategory}
                onChange={(event) => setSubcategory(event.target.value)}
                className="w-full px-3 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[12px] text-white/80 text-sm"
              >
                {['Salary', 'Freelance', 'Interest', 'Other Income'].map((value) => (
                  <option key={value} value={value} className="bg-[#1a2a4a]">{value}</option>
                ))}
              </select>
            </div>
            <GlassButton
              variant="secondary"
              onClick={() => dismissMutation.mutate()}
              disabled={!selectedIds.length || busy}
            >
              Not this income
            </GlassButton>
            <GlassButton
              onClick={() => confirmMutation.mutate()}
              disabled={!selectedIds.length || busy}
            >
              Confirm {selectedIds.length || ''}
            </GlassButton>
          </div>
        )}
      </DialogSurface>
    </div>
  );
}

export default function Income() {
  const [addOpen, setAddOpen] = useState(false);
  const [editSource, setEditSource] = useState(null);
  const [reviewSource, setReviewSource] = useState(null);
  const queryClient = useQueryClient();
  const currentMonth = format(new Date(), 'yyyy-MM');
  const { confirm, ConfirmDialog: DeleteConfirmDialog } = useConfirm();

  const { data: sourcesData, isLoading } = useQuery({
    queryKey: ['incomeSources'],
    queryFn: () => fetchIncomeSources(),
  });

  const { data: stats } = useQuery({
    queryKey: ['incomeStats', currentMonth],
    queryFn: () => fetchIncomeStats(currentMonth),
  });

  const { data: coverage } = useQuery({
    queryKey: ['incomeCoverage'],
    queryFn: fetchIncomeCoverage,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteIncomeSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
      queryClient.invalidateQueries({ queryKey: ['incomeStats'] });
    },
  });

  async function handleDelete(source) {
    const confirmed = await confirm({
      title: 'Delete Income Source',
      message: `Are you sure you want to delete "${source.source_name}"?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (confirmed) {
      deleteMutation.mutate(source.id);
    }
  }

  const handleEdit = (source) => {
    setEditSource(source);
    setAddOpen(true);
  };

  const handleCloseModal = () => {
    setAddOpen(false);
    setEditSource(null);
  };

  const sources = sourcesData?.items || [];

  return (
    <div>
      <DeleteConfirmDialog />
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Income Sources</h1>
          <p className="text-white/30 text-[0.8rem]">Track your income streams</p>
        </div>
        <GlassButton icon={<Plus size={15} />} onClick={() => setAddOpen(true)}>Add Source</GlassButton>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Expected Monthly" value={formatINR(stats?.total_expected_monthly)} icon={TrendingUp} color="text-emerald-400" delay={0.1} />
        <StatCard title="This Month" value={formatINR(stats?.total_detected_this_month)} icon={DollarSign} color="text-blue-400" delay={0.15} />
        <StatCard title="Total Sources" value={stats?.sources_count || 0} icon={Calendar} color="text-violet-400" delay={0.2} />
        <StatCard title="Active" value={stats?.active_sources_count || 0} icon={Check} color="text-amber-400" delay={0.25} />
      </div>

      {/* Income Cards */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 border-2 border-cyan-400/50 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : sources.length === 0 ? (
        <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-8 text-center">
          <DollarSign className="h-8 w-8 text-white/20 mx-auto mb-2" aria-hidden="true" />
          <p className="text-white/40 text-[0.9rem]">No income sources yet</p>
          <p className="text-white/25 text-[0.75rem] mt-1">Add your income sources to track earnings</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence>
            {sources.map((source, i) => (
              <motion.div
                key={source.id}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -100 }}
                transition={{ delay: i * 0.05 }}
                whileHover={{ scale: 1.01 }}
                className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
              >
                <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-[14px] bg-emerald-400/[0.1] border border-emerald-400/[0.12] flex items-center justify-center">
                      <DollarSign className="h-5 w-5 text-emerald-400/70" aria-hidden="true" />
                    </div>
                    <div>
                      <h3 className="text-white/80 text-[0.9rem]" style={{ fontWeight: 400 }}>{source.source_name}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[0.65rem] px-2 py-0.5 rounded-full ${frequencyColors[source.frequency] || frequencyColors.monthly}`}>
                          {source.frequency}
                        </span>
                        {source.enforce_current_month && (
                          <span className="text-[0.65rem] px-2 py-0.5 rounded-full bg-amber-400/[0.1] text-amber-400/70 border border-amber-400/[0.12]">
                            This month
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => handleEdit(source)} className="p-1.5 text-white/20 hover:text-white/50 hover:bg-white/[0.06] rounded-[8px] transition-colors" aria-label={`Edit ${source.source_name}`}>
                      <Edit2 size={13} />
                    </button>
                    <button onClick={() => handleDelete(source)} className="p-1.5 text-white/20 hover:text-rose-400/60 hover:bg-white/[0.06] rounded-[8px] transition-colors" aria-label={`Delete ${source.source_name}`}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-white/25 text-[0.65rem]">Expected</p>
                    <p className="text-white/80 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(source.expected_amount)}</p>
                  </div>
                  <div>
                    <p className="text-white/25 text-[0.65rem]">Last Detected</p>
                    <p className="text-white/80 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>
                      {source.last_detected_amount ? formatINR(source.last_detected_amount) : '--'}
                    </p>
                    {source.last_detected_date && (
                      <p className="text-white/20 text-[0.65rem]">
                        {format(new Date(source.last_detected_date), 'dd MMM yyyy')}
                      </p>
                    )}
                  </div>
                </div>
                {source.next_expected_date && (
                  <div className="mt-3 pt-3 border-t border-white/[0.06]">
                    <div className="flex items-center gap-2 text-white/30 text-[0.7rem]">
                      <Calendar size={12} aria-hidden="true" />
                      <span>Next expected: {format(new Date(source.next_expected_date), 'dd MMM yyyy')}</span>
                    </div>
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-white/[0.06] space-y-2">
                  <div className="text-white/25 text-[0.68rem]">
                    Applies from {format(new Date(`${source.effective_from}T00:00:00`), 'dd MMM yyyy')}
                    {source.effective_to
                      ? ` to ${format(new Date(`${source.effective_to}T00:00:00`), 'dd MMM yyyy')}`
                      : ''}
                  </div>
                  <button
                    type="button"
                    onClick={() => setReviewSource(source)}
                    className="inline-flex items-center gap-1.5 text-cyan-300/65 hover:text-cyan-200 text-[0.72rem] transition-colors"
                    aria-label={`Find past income for ${source.source_name}`}
                  >
                    <Search size={13} aria-hidden="true" />
                    Find past income
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      <AnimatePresence>
        {addOpen && (
          <AddIncomeModal
            open={addOpen}
            onClose={handleCloseModal}
            editSource={editSource}
            coverage={coverage}
            accounts={accounts}
            onFindPast={setReviewSource}
          />
        )}
        {reviewSource && (
          <IncomeMatchReview
            source={reviewSource}
            onClose={() => setReviewSource(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
