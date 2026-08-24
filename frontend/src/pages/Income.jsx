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
  confirmIncomeMatches, dismissIncomeMatches, recordActualIncome,
  previewActualIncomePeriod, confirmActualIncomePeriod,
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
  monthly: 'bg-emerald-400/[0.1] text-emerald-200 border border-emerald-400/[0.12]',
  quarterly: 'bg-blue-400/[0.1] text-blue-200 border border-blue-400/[0.12]',
  annual: 'bg-violet-400/[0.1] text-violet-200 border border-violet-400/[0.12]',
  one_time: 'bg-white/[0.06] text-ink-muted border border-white/[0.08]',
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
          <h3 id="income-modal-title" className="text-ink-primary text-[1.1rem]" style={{ fontWeight: 400 }}>
            {editSource ? 'Edit Expected Income' : 'Add Expected Income'}
          </h3>
          <button onClick={onClose} className="text-ink-muted hover:text-ink-secondary" aria-label="Close modal"><X size={18} /></button>
        </div>
        {error && (
          <div className="mb-4 p-3 bg-rose-400/[0.08] border border-rose-400/[0.15] rounded-[12px] flex items-center gap-2 text-rose-200 text-[0.8rem]" role="alert">
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
            label="Amount you usually expect (₹)"
            type="number"
            value={expectedAmount}
            onChange={(e) => setExpectedAmount(e.target.value)}
            placeholder="e.g., 50000"
            min="0.01"
            step="0.01"
          />
          <div>
            <label htmlFor="income-frequency" className="block text-ink-muted text-[0.75rem] mb-1.5" style={{ fontWeight: 400 }}>Frequency</label>
            <select
              id="income-frequency"
              value={frequency}
              onChange={(e) => handleFrequencyChange(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.12] rounded-[14px] text-ink-primary text-[0.85rem] focus:outline-none focus:border-cyan-400/30"
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
          <p className="text-ink-muted text-[0.7rem] -mt-2">
            This is a reminder and matching guide only. It does not add money to your Dashboard. Use “Record income” for money you actually received.
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
              <label htmlFor="income-account" className="block text-ink-muted text-[0.75rem] mb-1.5">Account (optional)</label>
              <select
                id="income-account"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-ink-primary text-[0.85rem]"
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
              <label htmlFor="income-payment-rail" className="block text-ink-muted text-[0.75rem] mb-1.5">Paid through (optional)</label>
              <select
                id="income-payment-rail"
                value={paymentRail}
                onChange={(e) => setPaymentRail(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-ink-primary text-[0.85rem]"
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
                className="mt-0.5 h-4 w-4 rounded border-white/[0.2] bg-white/[0.05] text-cyan-200"
              />
              <div>
                <label htmlFor="findPastIncome" className="text-ink-secondary text-[0.85rem] cursor-pointer">Find past matching income after saving</label>
                <p className="text-ink-muted text-[0.7rem] mt-0.5">You review every suggested credit before GODFIN changes anything.</p>
              </div>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <GlassButton type="button" variant="secondary" onClick={onClose} className="flex-1 justify-center">Cancel</GlassButton>
            <GlassButton type="submit" disabled={isLoading} className="flex-1 justify-center">
              {isLoading ? 'Saving...' : editSource ? 'Update reminder' : 'Add expected source'}
            </GlassButton>
          </div>
        </form>
      </DialogSurface>
    </div>
  );
}


function RecordIncomeModal({ onClose, sources, accounts }) {
  const today = new Date().toISOString().split('T')[0];
  const currentMonth = today.slice(0, 7);
  const [mode, setMode] = useState('single');
  const [incomeSourceId, setIncomeSourceId] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState(
    accounts.find((account) => account.is_active !== false)?.id || '',
  );
  const [subcategory, setSubcategory] = useState('Salary');
  const [incomeDate, setIncomeDate] = useState(today);
  const [startMonth, setStartMonth] = useState(`${today.slice(0, 4)}-01`);
  const [endMonth, setEndMonth] = useState(currentMonth);
  const [paymentDay, setPaymentDay] = useState('1');
  const [note, setNote] = useState('');
  const [reference, setReference] = useState('');
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const queryClient = useQueryClient();

  const effectiveAccountId = accountId
    || accounts.find((account) => account.is_active !== false)?.id
    || '';

  const refreshFinancialViews = () => {
    [
      'transactions', 'dashboardStats', 'dashboardMonths', 'cashFlow', 'report',
      'financialProfile', 'incomeStats', 'incomeSources', 'behaviorInsights',
      'budget', 'patterns',
    ].forEach((queryKey) => queryClient.invalidateQueries({ queryKey: [queryKey] }));
  };

  const finish = () => {
    refreshFinancialViews();
    onClose();
  };
  const singleMutation = useMutation({
    mutationFn: recordActualIncome,
    onSuccess: finish,
    onError: (err) => setError(err.message || 'GODFIN could not record this income.'),
  });
  const previewMutation = useMutation({
    mutationFn: previewActualIncomePeriod,
    onSuccess: (data) => setPreview(data),
    onError: (err) => setError(err.message || 'GODFIN could not prepare this history.'),
  });
  const confirmMutation = useMutation({
    mutationFn: confirmActualIncomePeriod,
    onSuccess: finish,
    onError: (err) => setError(err.message || 'GODFIN could not save these entries.'),
  });

  const basePayload = () => ({
    source_name: sourceName.trim(),
    income_source_id: incomeSourceId || null,
    amount: Number(amount),
    account_id: effectiveAccountId,
    subcategory,
    note: note.trim() || null,
    reference: reference.trim() || null,
  });
  const periodPayload = () => ({
    ...basePayload(),
    start_month: startMonth,
    end_month: endMonth,
    payment_day: Number(paymentDay),
  });
  const validate = () => {
    if (!sourceName.trim()) return 'Enter where this income came from.';
    if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) return 'Enter an amount greater than zero.';
    if (!effectiveAccountId) return 'Choose the account that received this income.';
    if (mode === 'single' && !incomeDate) return 'Choose the date you received the income.';
    if (mode === 'history' && (!startMonth || !endMonth)) return 'Choose the first and last month.';
    if (mode === 'history' && startMonth > endMonth) return 'The last month cannot be before the first month.';
    return '';
  };
  const submit = (event) => {
    event.preventDefault();
    setError('');
    const validation = validate();
    if (validation) {
      setError(validation);
      return;
    }
    if (mode === 'single') {
      singleMutation.mutate({ ...basePayload(), date: incomeDate });
      return;
    }
    setPreview(null);
    previewMutation.mutate(periodPayload());
  };
  const chooseSource = (id) => {
    setIncomeSourceId(id);
    const selected = sources.find((source) => source.id === id);
    if (selected) setSourceName(selected.source_name);
    setPreview(null);
  };
  const busy = singleMutation.isPending || previewMutation.isPending || confirmMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="presentation">
      <DialogSurface
        labelledBy="record-income-title"
        onClose={onClose}
        className="relative w-full max-w-2xl max-h-[92vh] overflow-y-auto mx-4 rounded-[24px] bg-[#0d2040]/95 border border-white/[0.15] p-6 shadow-[0_16px_64px_rgba(0,0,0,0.35)]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="record-income-title" className="text-ink-primary text-lg">Record money you received</h2>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              This changes your real income totals. An expected source is only a reminder and never adds money by itself.
            </p>
          </div>
          <button type="button" onClick={onClose} className="p-2 text-ink-muted hover:text-ink-secondary" aria-label="Close income form">
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-2 rounded-[14px] bg-white/[0.04] p-1" role="tablist" aria-label="Income entry type">
          {[
            ['single', 'One payment'],
            ['history', 'Monthly history'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              onClick={() => { setMode(value); setPreview(null); setError(''); }}
              className={`rounded-[11px] px-3 py-2 text-sm transition-colors ${mode === value ? 'bg-cyan-400/15 text-cyan-200' : 'text-ink-muted hover:text-ink-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-5 space-y-4">
          {sources.length > 0 && (
            <div>
              <label htmlFor="actual-income-source" className="block text-ink-muted text-xs mb-1.5">Use an expected source (optional)</label>
              <select
                id="actual-income-source"
                value={incomeSourceId}
                onChange={(event) => chooseSource(event.target.value)}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-ink-primary text-sm"
              >
                <option value="" className="bg-[#1a2a4a]">Enter a name yourself</option>
                {sources.map((source) => (
                  <option key={source.id} value={source.id} className="bg-[#1a2a4a]">{source.source_name}</option>
                ))}
              </select>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="actual-income-name" className="block text-ink-muted text-xs mb-1.5">Where did it come from?</label>
              <GlassInput
                id="actual-income-name"
                value={sourceName}
                onChange={(event) => { setSourceName(event.target.value); setPreview(null); }}
                placeholder="For example, salary or freelance work"
                maxLength={100}
              />
            </div>
            <div>
              <label htmlFor="actual-income-amount" className="block text-ink-muted text-xs mb-1.5">Amount received each time</label>
              <GlassInput
                id="actual-income-amount"
                type="number"
                min="0.01"
                step="0.01"
                value={amount}
                onChange={(event) => { setAmount(event.target.value); setPreview(null); }}
                placeholder="₹0"
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="actual-income-account" className="block text-ink-muted text-xs mb-1.5">Account that received it</label>
              <select
                id="actual-income-account"
                value={effectiveAccountId}
                onChange={(event) => { setAccountId(event.target.value); setPreview(null); }}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-ink-primary text-sm"
              >
                <option value="" className="bg-[#1a2a4a]">Choose an account</option>
                {accounts.filter((account) => account.is_active !== false).map((account) => (
                  <option key={account.id} value={account.id} className="bg-[#1a2a4a]">
                    {account.nickname || account.bank} · {account.last_4_digits}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="actual-income-kind" className="block text-ink-muted text-xs mb-1.5">Kind of income</label>
              <select
                id="actual-income-kind"
                value={subcategory}
                onChange={(event) => { setSubcategory(event.target.value); setPreview(null); }}
                className="w-full px-3.5 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[14px] text-ink-primary text-sm"
              >
                {['Salary', 'Freelance', 'Interest', 'Other Income'].map((value) => (
                  <option key={value} value={value} className="bg-[#1a2a4a]">{value}</option>
                ))}
              </select>
            </div>
          </div>

          {mode === 'single' ? (
            <div>
              <label htmlFor="actual-income-date" className="block text-ink-muted text-xs mb-1.5">Date received</label>
              <GlassInput id="actual-income-date" type="date" max={today} value={incomeDate} onChange={(event) => setIncomeDate(event.target.value)} />
            </div>
          ) : (
            <div className="rounded-[16px] border border-cyan-400/[0.1] bg-cyan-400/[0.04] p-4">
              <p className="text-sm text-ink-secondary">Add the same amount for several months</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">You will see every date and amount before anything is saved. A later rate starts as a separate entry, so earlier months never change.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div>
                  <label htmlFor="actual-income-start" className="block text-ink-muted text-xs mb-1.5">First month</label>
                  <GlassInput id="actual-income-start" type="month" value={startMonth} onChange={(event) => { setStartMonth(event.target.value); setPreview(null); }} />
                </div>
                <div>
                  <label htmlFor="actual-income-end" className="block text-ink-muted text-xs mb-1.5">Last month</label>
                  <GlassInput id="actual-income-end" type="month" max={currentMonth} value={endMonth} onChange={(event) => { setEndMonth(event.target.value); setPreview(null); }} />
                </div>
                <div>
                  <label htmlFor="actual-income-day" className="block text-ink-muted text-xs mb-1.5">Day received</label>
                  <GlassInput id="actual-income-day" type="number" min="1" max="31" value={paymentDay} onChange={(event) => { setPaymentDay(event.target.value); setPreview(null); }} />
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="actual-income-reference" className="block text-ink-muted text-xs mb-1.5">Reference (optional)</label>
              <GlassInput id="actual-income-reference" value={reference} maxLength={64} onChange={(event) => { setReference(event.target.value); setPreview(null); }} placeholder="Payslip or payment reference" />
            </div>
            <div>
              <label htmlFor="actual-income-note" className="block text-ink-muted text-xs mb-1.5">Note (optional)</label>
              <GlassInput id="actual-income-note" value={note} maxLength={2000} onChange={(event) => { setNote(event.target.value); setPreview(null); }} placeholder="Anything you want to remember" />
            </div>
          </div>

          {error && <div className="rounded-[12px] border border-rose-400/20 bg-rose-400/[0.08] p-3 text-sm text-rose-200" role="alert">{error}</div>}

          {preview && (
            <div className="rounded-[16px] border border-emerald-400/[0.15] bg-emerald-400/[0.05] p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-ink-secondary">Check these {preview.entries.length} entries</p>
                  <p className="text-xs text-ink-muted">Total: {formatINR(preview.total_amount)}</p>
                </div>
                <Check size={20} className="text-emerald-200" aria-hidden="true" />
              </div>
              <div className="mt-3 max-h-48 overflow-y-auto rounded-[10px] border border-white/[0.06] divide-y divide-white/[0.05]">
                {preview.entries.map((entry) => (
                  <div key={entry.date} className="flex items-center justify-between px-3 py-2 text-xs">
                    <span className="text-ink-muted">{format(new Date(`${entry.date}T00:00:00`), 'dd MMM yyyy')}</span>
                    <span className="text-ink-secondary tabular-nums">{formatINR(entry.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <GlassButton type="button" variant="secondary" onClick={onClose} className="flex-1 justify-center">Cancel</GlassButton>
            {mode === 'history' && preview ? (
              <GlassButton
                type="button"
                disabled={busy}
                onClick={() => confirmMutation.mutate({
                  ...periodPayload(),
                  preview_fingerprint: preview.preview_fingerprint,
                  confirm: true,
                })}
                className="flex-1 justify-center"
              >
                {confirmMutation.isPending ? 'Saving…' : `Confirm ${preview.entries.length} entries`}
              </GlassButton>
            ) : (
              <GlassButton type="submit" disabled={busy} className="flex-1 justify-center">
                {busy ? 'Checking…' : mode === 'single' ? 'Record income' : 'Preview entries'}
              </GlassButton>
            )}
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
            <h3 id="income-match-title" className="text-ink-primary text-lg">Review past income</h3>
            <p className="text-ink-muted text-xs mt-1">
              {source.source_name} · {source.effective_from} onward. Nothing changes until you confirm it.
            </p>
          </div>
          <button onClick={onClose} className="p-2 text-ink-muted hover:text-ink-secondary" aria-label="Close past income review">
            <X size={18} />
          </button>
        </div>

        {scanMutation.data && (
          <div className="mb-4 rounded-[14px] border border-cyan-400/[0.12] bg-cyan-400/[0.05] p-3 text-xs text-ink-muted">
            Checked {scanMutation.data.scanned} credits from {scanMutation.data.coverage_start} to {scanMutation.data.coverage_end}. Found {scanMutation.data.strong} strong and {scanMutation.data.uncertain} uncertain match{scanMutation.data.uncertain === 1 ? '' : 'es'}. Safely excluded {scanMutation.data.excluded_unsafe} refund, transfer, reversal, or locked credit{scanMutation.data.excluded_unsafe === 1 ? '' : 's'}.
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-[12px] border border-rose-400/20 bg-rose-400/[0.08] p-3 text-sm text-rose-200" role="alert">
            {error.message || 'GODFIN could not finish the income review.'}
          </div>
        )}

        {matchesLoading || scanMutation.isPending ? (
          <div className="py-12 flex items-center justify-center gap-2 text-ink-muted text-sm">
            <Loader2 size={18} className="animate-spin" /> Checking your local transactions…
          </div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center">
            <Check className="mx-auto text-emerald-200 mb-2" size={26} />
            <p className="text-ink-secondary">No unreviewed matches</p>
            <p className="text-ink-muted text-xs mt-1">GODFIN did not guess from amount alone.</p>
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
                  className="mt-1 h-4 w-4 rounded border-white/20 bg-white/5 text-cyan-200"
                  aria-label={`Select ${item.merchant} credit from ${item.date}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-ink-secondary text-sm">{item.merchant}</span>
                    <span className="text-ink-primary tabular-nums text-sm">{formatINR(item.amount)}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[0.68rem] text-ink-muted">
                    <span>{item.date}</span><span>·</span><span>{item.instrument}</span>
                    <span className={item.strength === 'strong' ? 'text-emerald-200' : 'text-amber-200'}>
                      {item.strength === 'strong' ? 'Strong match' : 'Needs a closer look'}
                    </span>
                  </div>
                  <ul className="mt-1 text-[0.68rem] text-ink-muted list-disc list-inside">
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
              <label htmlFor="income-match-kind" className="block text-ink-muted text-xs mb-1.5">What kind of income is this?</label>
              <select
                id="income-match-kind"
                value={subcategory}
                onChange={(event) => setSubcategory(event.target.value)}
                className="w-full px-3 py-2.5 bg-white/[0.06] border border-white/[0.12] rounded-[12px] text-ink-primary text-sm"
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
  const [recordOpen, setRecordOpen] = useState(false);
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
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-ink-primary text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Income</h1>
          <p className="text-ink-muted text-[0.8rem]">Record money you received, and keep expected payments as reminders.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <GlassButton variant="secondary" icon={<Calendar size={15} />} onClick={() => setAddOpen(true)}>Add expected source</GlassButton>
          <GlassButton icon={<Plus size={15} />} onClick={() => setRecordOpen(true)}>Record income</GlassButton>
        </div>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Expected this month" value={formatINR(stats?.total_expected_monthly)} icon={TrendingUp} color="text-emerald-200" delay={0.1} />
        <StatCard title="Actually received" value={formatINR(stats?.total_detected_this_month)} icon={DollarSign} color="text-blue-200" delay={0.15} />
        <StatCard title="Expected sources" value={stats?.sources_count || 0} icon={Calendar} color="text-violet-200" delay={0.2} />
        <StatCard title="Active reminders" value={stats?.active_sources_count || 0} icon={Check} color="text-amber-200" delay={0.25} />
      </div>

      {/* Income Cards */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 border-2 border-cyan-400/50 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : sources.length === 0 ? (
        <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-8 text-center">
          <DollarSign className="h-8 w-8 text-ink-muted mx-auto mb-2" aria-hidden="true" />
          <p className="text-ink-muted text-[0.9rem]">No expected income reminders yet</p>
          <p className="text-ink-muted text-[0.75rem] mt-1">You can still record money you already received.</p>
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
                      <DollarSign className="h-5 w-5 text-emerald-200" aria-hidden="true" />
                    </div>
                    <div>
                      <h3 className="text-ink-primary text-[0.9rem]" style={{ fontWeight: 400 }}>{source.source_name}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[0.65rem] px-2 py-0.5 rounded-full ${frequencyColors[source.frequency] || frequencyColors.monthly}`}>
                          {source.frequency}
                        </span>
                        {source.enforce_current_month && (
                          <span className="text-[0.65rem] px-2 py-0.5 rounded-full bg-amber-400/[0.1] text-amber-200 border border-amber-400/[0.12]">
                            This month
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => handleEdit(source)} className="p-1.5 text-ink-muted hover:text-ink-muted hover:bg-white/[0.06] rounded-[8px] transition-colors" aria-label={`Edit ${source.source_name}`}>
                      <Edit2 size={13} />
                    </button>
                    <button onClick={() => handleDelete(source)} className="p-1.5 text-ink-muted hover:text-rose-200 hover:bg-white/[0.06] rounded-[8px] transition-colors" aria-label={`Delete ${source.source_name}`}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-ink-muted text-[0.65rem]">Expected</p>
                    <p className="text-ink-primary text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(source.expected_amount)}</p>
                  </div>
                  <div>
                    <p className="text-ink-muted text-[0.65rem]">Last Detected</p>
                    <p className="text-ink-primary text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>
                      {source.last_detected_amount ? formatINR(source.last_detected_amount) : '--'}
                    </p>
                    {source.last_detected_date && (
                      <p className="text-ink-muted text-[0.65rem]">
                        {format(new Date(source.last_detected_date), 'dd MMM yyyy')}
                      </p>
                    )}
                  </div>
                </div>
                {source.next_expected_date && (
                  <div className="mt-3 pt-3 border-t border-white/[0.06]">
                    <div className="flex items-center gap-2 text-ink-muted text-[0.7rem]">
                      <Calendar size={12} aria-hidden="true" />
                      <span>Next expected: {format(new Date(source.next_expected_date), 'dd MMM yyyy')}</span>
                    </div>
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-white/[0.06] space-y-2">
                  <div className="text-ink-muted text-[0.68rem]">
                    Applies from {format(new Date(`${source.effective_from}T00:00:00`), 'dd MMM yyyy')}
                    {source.effective_to
                      ? ` to ${format(new Date(`${source.effective_to}T00:00:00`), 'dd MMM yyyy')}`
                      : ''}
                  </div>
                  <button
                    type="button"
                    onClick={() => setReviewSource(source)}
                    className="inline-flex items-center gap-1.5 text-cyan-200 hover:text-cyan-200 text-[0.72rem] transition-colors"
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
        {recordOpen && (
          <RecordIncomeModal
            onClose={() => setRecordOpen(false)}
            sources={sources}
            accounts={accounts}
          />
        )}
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
