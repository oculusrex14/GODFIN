import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { addDays, format, differenceInDays } from 'date-fns';
import {
  Target, Plus, Trash2, Sparkles, PiggyBank, Gauge, Wallet,
  Repeat, CreditCard, TrendingUp, RefreshCw, X, CircleDollarSign,
  AlertTriangle, History,
} from 'lucide-react';
import {
  fetchGoals, createGoal, deleteGoal, simulateGoal,
  fetchRecurring, detectRecurring,
  fetchFinancialProfile, fetchGoalContributions, createGoalContribution,
  voidGoalContribution, fetchGoalContributionSuggestions,
  decideGoalContributionSuggestion,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import CalculationInfo from '../components/CalculationInfo';
import { useToast } from '../context/ToastContext';

const MIN_GOAL_DATE = format(addDays(new Date(), 1), 'yyyy-MM-dd');

function formatINR(amount) {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function HealthGauge({ label, value, max = 100, invert = false, icon: Icon, calculation }) {
  const safeValue = value != null && !isNaN(value) ? value : 0;
  const pct = max > 0 ? Math.min(safeValue / max, 1) * 100 : 0;
  const good = invert ? pct < 40 : pct > 60;
  const warn = invert ? pct >= 40 && pct < 70 : pct >= 30 && pct <= 60;
  const gradientClass = good ? 'from-emerald-400 to-emerald-500' : warn ? 'from-amber-400 to-amber-500' : 'from-rose-400 to-rose-500';
  const textColor = good ? 'text-emerald-400/80' : warn ? 'text-amber-400/80' : 'text-rose-400/80';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon size={13} className="text-white/30" aria-hidden="true" />
          <span className="text-white/40 text-[0.7rem]">{label}</span>
          {calculation && <CalculationInfo title={label} {...calculation} />}
        </div>
        <span className={`text-[0.8rem] tabular-nums ${textColor}`} style={{ fontWeight: 500 }}>
          {value != null && !isNaN(value) ? `${value.toFixed(1)}%` : '--'}
        </span>
      </div>
      <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className={`h-full rounded-full bg-gradient-to-r ${gradientClass}`}
        />
      </div>
    </div>
  );
}

export default function Budget() {
  const queryClient = useQueryClient();
  const { success: showSuccess } = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    target_amount: '',
    current_saved: '0',
    deadline_date: '',
    annual_return_rate: '0',
  });
  const [simResult, setSimResult] = useState(null);
  const [simGoalId, setSimGoalId] = useState(null);
  const [savingsGoal, setSavingsGoal] = useState(null);
  const [savingsForm, setSavingsForm] = useState({
    amount: '',
    entry_type: 'deposit',
    contribution_date: format(new Date(), 'yyyy-MM-dd'),
    note: '',
  });
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  const { data: goals = [] } = useQuery({
    queryKey: ['goals'],
    queryFn: fetchGoals,
  });

  const { data: profile } = useQuery({
    queryKey: ['financialProfile'],
    queryFn: fetchFinancialProfile,
  });

  const { data: recurring = [] } = useQuery({
    queryKey: ['recurring'],
    queryFn: fetchRecurring,
  });

  const { data: suggestionData = { enabled: false, items: [] } } = useQuery({
    queryKey: ['goalContributionSuggestions'],
    queryFn: fetchGoalContributionSuggestions,
  });
  const suggestions = suggestionData.items || [];

  const { data: contributions = [] } = useQuery({
    queryKey: ['goalContributions', savingsGoal?.id],
    queryFn: () => fetchGoalContributions(savingsGoal.id, true),
    enabled: Boolean(savingsGoal),
  });

  const createMutation = useMutation({
    mutationFn: createGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({ queryKey: ['financialProfile'] });
      setAddOpen(false);
      setForm({
        name: '',
        target_amount: '',
        current_saved: '0',
        deadline_date: '',
        annual_return_rate: '0',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals'] }),
  });

  const detectMutation = useMutation({
    mutationFn: detectRecurring,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['recurring'] });
      showSuccess(
        `Recurring scan: ${result.created} created, ${result.updated} updated, ${result.deactivated} retired across ${result.scanned} merchant-account groups.`
      );
    },
  });

  const simulateMutation = useMutation({
    mutationFn: simulateGoal,
    onSuccess: (data, goalId) => {
      setSimResult(data);
      setSimGoalId(goalId);
    },
  });

  const contributionMutation = useMutation({
    mutationFn: ({ goalId, data }) => createGoalContribution(goalId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({
        queryKey: ['goalContributions', savingsGoal?.id],
      });
      setSavingsForm({
        amount: '',
        entry_type: 'deposit',
        contribution_date: format(new Date(), 'yyyy-MM-dd'),
        note: '',
      });
      showSuccess('Goal savings updated.');
    },
  });

  const voidContributionMutation = useMutation({
    mutationFn: ({ goalId, contributionId }) =>
      voidGoalContribution(
        goalId,
        contributionId,
        'Voided by the user from contribution history.'
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({
        queryKey: ['goalContributions', savingsGoal?.id],
      });
      showSuccess('Contribution voided; history was preserved.');
    },
  });

  const suggestionMutation = useMutation({
    mutationFn: ({ suggestionId, goalId }) =>
      decideGoalContributionSuggestion(suggestionId, goalId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['goalContributionSuggestions'],
      });
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      showSuccess('Deposit review saved.');
    },
  });

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Budget & Goals</h1>
          <p className="text-white/30 text-[0.8rem]">Track goals, subscriptions & financial health</p>
        </div>
        <GlassButton icon={<Plus size={15} />} onClick={() => setAddOpen(true)}>New Goal</GlassButton>
      </motion.div>

      {/* Financial Health */}
      {profile && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5 mb-6"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Financial Health</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <HealthGauge
              label="Savings Rate"
              value={profile.savings_rate}
              icon={PiggyBank}
              calculation={{
                meaning: 'The portion of income left after included expenses.',
                formula: '(income − expenses) ÷ income',
                inputs: 'Verified income and non-transfer expenses.',
                period: 'Current financial-profile window.',
                caveat: 'Unavailable when verified income is zero.',
              }}
            />
            <HealthGauge
              label="Impulse Index"
              value={profile.impulse_index}
              invert
              icon={Gauge}
              calculation={{
                meaning: 'The share of debit transactions that are small flexible-category purchases.',
                formula: 'small flexible debit count ÷ total debit count × 100',
                inputs: 'Debits below ₹500 in flexible categories and all included debits.',
                period: 'Current financial-profile window.',
                caveat: 'Category quality affects this estimate; it is not a psychological diagnosis.',
              }}
            />
            <HealthGauge
              label="Fixed Expense Ratio"
              value={profile.fixed_expense_ratio}
              invert
              icon={Wallet}
              calculation={{
                meaning: 'How much verified income is committed to fixed expenses.',
                formula: 'fixed expenses ÷ income',
                inputs: 'Fixed-category expenses and verified income.',
                period: 'Current financial-profile window.',
                caveat: 'Review categories and income completeness before interpreting this ratio.',
              }}
            />
            <HealthGauge
              label="Recurring Burden"
              value={profile.recurring_burden}
              invert
              icon={Repeat}
              calculation={{
                meaning: 'The portion of income used by detected recurring payments.',
                formula: 'recurring expenses ÷ income',
                inputs: 'Confirmed recurring transactions and verified income.',
                period: 'Current financial-profile window.',
                caveat: 'New or irregular recurring payments may not be detected yet.',
              }}
            />
            <HealthGauge
              label="Subscription Dependency"
              value={profile.subscription_dependency}
              invert
              icon={CreditCard}
              calculation={{
                meaning: 'The portion of expenses attributed to confirmed subscriptions.',
                formula: 'subscription expenses ÷ total expenses',
                inputs: 'Confirmed subscriptions and non-transfer expenses.',
                period: 'Current financial-profile window.',
                caveat: 'Unconfirmed subscription suggestions are excluded.',
              }}
            />
            <HealthGauge
              label="Lifestyle Inflation"
              value={profile.lifestyle_inflation}
              max={200}
              invert
              icon={TrendingUp}
              calculation={{
                meaning: 'How discretionary spending changed relative to the comparison period.',
                formula: '(current flexible spend − prior flexible spend) ÷ prior flexible spend × 100',
                inputs: 'Discretionary-category expenses in comparable periods.',
                period: 'Current window versus the previous comparable window.',
                caveat: 'Short or incomplete periods can create large swings.',
              }}
            />
          </div>
        </motion.div>
      )}

      {/* Goals */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="mb-6">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider flex items-center gap-1.5" style={{ fontWeight: 500 }}>
            <Target size={14} /> Goals ({goals.length})
          </h2>
          {suggestions.length > 0 && (
            <button
              type="button"
              onClick={() => setSuggestionsOpen(true)}
              className="inline-flex items-center gap-1 rounded-full border border-amber-400/25 bg-amber-400/10 px-2 py-0.5 text-[0.65rem] text-amber-300/90 hover:bg-amber-400/15"
              aria-label={`${suggestions.length} deposit contribution suggestions need review`}
            >
              <AlertTriangle size={11} />
              {suggestions.length} to review
            </button>
          )}
        </div>
        {goals.length === 0 ? (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-8 text-center">
            <Target className="h-8 w-8 text-white/20 mx-auto mb-2" />
            <p className="text-sm text-white/40">No goals yet. Create one to start tracking.</p>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-4">
            {goals.map((goal) => {
              const daysLeft = Math.max(0, differenceInDays(new Date(goal.deadline_date), new Date()));
              const progress = goal.target_amount > 0 ? Math.min((goal.current_saved / goal.target_amount) * 100, 100) : 0;
              return (
                <motion.div
                  key={goal.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  whileHover={{ scale: 1.01 }}
                  className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
                >
                  <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-white/80 text-[0.9rem]" style={{ fontWeight: 400 }}>{goal.name}</h3>
                        {suggestions.some((item) => item.goal_id === goal.id) && (
                          <button
                            type="button"
                            onClick={() => setSuggestionsOpen(true)}
                            className="rounded-full p-1 text-amber-300/80 hover:bg-amber-400/10"
                            aria-label={`Review detected deposits for ${goal.name}`}
                          >
                            <AlertTriangle size={13} />
                          </button>
                        )}
                      </div>
                      <p className="text-white/25 text-[0.7rem] mt-0.5">
                        {daysLeft} days left · {format(new Date(goal.deadline_date), 'dd MMM yyyy')}
                      </p>
                      <p className="text-white/25 text-[0.65rem] mt-0.5">
                        Expected return {(goal.annual_return_rate * 100).toFixed(1)}% yearly
                      </p>
                    </div>
                    <button
                      onClick={() => deleteMutation.mutate(goal.id)}
                      className="text-white/15 hover:text-rose-400/60 transition-colors p-1"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div className="flex items-end justify-between mb-2">
                    <span className="text-white/90 text-[1.2rem] tabular-nums" style={{ fontWeight: 300 }}>{formatINR(goal.current_saved)}</span>
                    <span className="text-white/30 text-[0.7rem]">of {formatINR(goal.target_amount)}</span>
                  </div>
                  <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden mb-3">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                      className={`h-full rounded-full ${progress >= 100 ? 'bg-gradient-to-r from-emerald-400 to-emerald-500' : 'bg-gradient-to-r from-cyan-400 to-blue-400'}`}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      onClick={() => simulateMutation.mutate(goal.id)}
                      disabled={simulateMutation.isPending && simGoalId === goal.id}
                      className="text-cyan-400/50 text-[0.7rem] hover:text-cyan-300/70 transition-colors flex items-center gap-1"
                    >
                      <Sparkles size={12} className={simulateMutation.isPending && simGoalId === goal.id ? 'animate-spin' : ''} />
                      {simulateMutation.isPending && simGoalId === goal.id ? 'Simulating...' : 'Run Simulation'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSavingsGoal(goal)}
                      className="flex min-h-9 items-center gap-1.5 rounded-lg border border-[#54E1D0]/20 bg-[#17C3B2]/[0.08] px-3 text-[#8EF1E4]/85 hover:bg-[#17C3B2]/[0.13] text-[0.7rem]"
                    >
                      <CircleDollarSign size={12} />
                      Add savings
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </motion.div>

      {/* Recurring */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider flex items-center gap-1.5" style={{ fontWeight: 500 }}>
            <Repeat size={14} /> Recurring ({recurring.length})
          </h2>
          <button
            onClick={() => detectMutation.mutate()}
            disabled={detectMutation.isPending}
            className="text-white/30 text-[0.7rem] hover:text-white/60 transition-colors flex items-center gap-1"
          >
            <RefreshCw size={12} className={detectMutation.isPending ? 'animate-spin' : ''} /> {detectMutation.isPending ? 'Detecting...' : 'Re-detect'}
          </button>
        </div>
        {recurring.length === 0 ? (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-8 text-center">
            <Repeat className="h-8 w-8 text-white/20 mx-auto mb-2" />
            <p className="text-sm text-white/40">No recurring patterns detected yet.</p>
          </div>
        ) : (
          <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]">
            <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
            <div className="divide-y divide-white/[0.04]">
              {recurring.map((p) => (
                <div key={p.id} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-white/70 text-[0.85rem] flex items-center gap-2">
                      {p.merchant}
                      {p.review_required && (
                        <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-[0.6rem] text-amber-300/80">
                          Review candidate
                        </span>
                      )}
                    </p>
                    <p className="text-white/25 text-[0.7rem]">
                      {p.frequency} · {p.category || 'Uncategorized'}
                      {p.next_expected && ` · Next: ${format(new Date(p.next_expected), 'dd MMM')}`}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-white/70 text-[0.85rem] tabular-nums">{formatINR(p.avg_amount)}</p>
                    <p className="text-white/20 text-[0.6rem]">
                      {p.times_detected}x · {Math.round((p.confidence || 0) * 100)}% confidence
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </motion.div>

      {/* Simulation Results Modal */}
      <AnimatePresence>
        {simResult && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setSimResult(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-md mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-white/90 text-[1.1rem] flex items-center gap-2" style={{ fontWeight: 400 }}>
                  <Sparkles size={16} className="text-cyan-400/60" /> Simulation Results
                </h3>
                <button onClick={() => setSimResult(null)} className="text-white/30 hover:text-white/60"><X size={18} /></button>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-white/40 text-[0.8rem]">Required Monthly Saving</span>
                  <span className="text-white/90 text-[0.95rem] tabular-nums" style={{ fontWeight: 500 }}>{formatINR(simResult.required_monthly)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-white/40 text-[0.8rem]">Current Flexible Spend</span>
                  <span className="text-white/70 text-[0.85rem] tabular-nums">{formatINR(simResult.flexible_spend)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-white/40 text-[0.8rem]">Max Saveable</span>
                  <span className="text-white/70 text-[0.85rem] tabular-nums">{formatINR(simResult.max_saveable)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-white/40 text-[0.8rem]">Months Remaining</span>
                  <span className="text-white/70 text-[0.85rem] tabular-nums">{simResult.months_remaining}</span>
                </div>

                <div className="h-[1px] bg-white/[0.08] my-2" />

                <div className="flex justify-between items-center">
                  <span className="text-white/40 text-[0.8rem]">Feasibility</span>
                  <span className={`text-[0.85rem] px-2.5 py-0.5 rounded-full ${
                    simResult.is_feasible === null
                      ? 'bg-amber-500/10 text-amber-300'
                      : simResult.is_feasible
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-rose-500/10 text-rose-400'
                  }`}>
                    {simResult.is_feasible === null
                      ? 'Insufficient history'
                      : simResult.is_feasible
                        ? 'Feasible'
                        : 'Not Feasible'}
                  </span>
                </div>

                {simResult.is_feasible === false && simResult.extended_deadline_months && (
                  <div className="flex justify-between items-center">
                    <span className="text-white/40 text-[0.8rem]">Extended Timeline</span>
                    <span className="text-amber-400/80 text-[0.85rem] tabular-nums">{simResult.extended_deadline_months} months needed</span>
                  </div>
                )}

                {simResult.pressure_savings && Object.keys(simResult.pressure_savings).length > 0 && (
                  <>
                    <div className="h-[1px] bg-white/[0.08] my-2" />
                    <p className="text-white/30 text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 500 }}>Pressure Levels</p>
                    {Object.entries(simResult.pressure_savings).map(([level, amount]) => (
                      <div key={level} className="flex justify-between items-center">
                        <span className="text-white/40 text-[0.8rem] capitalize">{level}</span>
                        <span className="text-white/60 text-[0.85rem] tabular-nums">{formatINR(amount)}/mo</span>
                      </div>
                    ))}
                  </>
                )}
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 text-[0.7rem] leading-relaxed text-white/35">
                  {simResult.coverage_months > 0 ? (
                    <p>
                      Capacity uses {simResult.coverage_months} complete month{simResult.coverage_months === 1 ? '' : 's'}
                      {simResult.coverage_start && simResult.coverage_end
                        ? ` (${simResult.coverage_start} to ${simResult.coverage_end})`
                        : ''}. Baseline surplus {formatINR(simResult.baseline_surplus)} plus reducible flexible spend {formatINR(simResult.reducible_flexible_spend)}.
                    </p>
                  ) : (
                    <p>GODFIN needs at least two complete months of transaction history before estimating saving capacity.</p>
                  )}
                  <p className="mt-1">{simResult.caveat}</p>
                  <p className="mt-1 text-white/25">Calculation version {simResult.calculation_version}; contributions are modeled at month end.</p>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Goal savings ledger */}
      <AnimatePresence>
        {savingsGoal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="relative max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-[24px] border border-white/[0.15] bg-[#0d2040]/95 p-6 shadow-[0_16px_64px_rgba(0,0,0,0.3)] backdrop-blur-[32px] mx-4"
              role="dialog"
              aria-modal="true"
              aria-labelledby="goal-savings-title"
            >
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h3 id="goal-savings-title" className="text-white/90 text-[1.1rem]">
                    Update {savingsGoal.name}
                  </h3>
                  <p className="mt-1 text-[0.72rem] text-white/30">Every change stays in an auditable ledger.</p>
                </div>
                <button onClick={() => setSavingsGoal(null)} className="text-white/30 hover:text-white/60" aria-label="Close savings history">
                  <X size={18} />
                </button>
              </div>
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  contributionMutation.mutate({
                    goalId: savingsGoal.id,
                    data: {
                      ...savingsForm,
                      amount: parseFloat(savingsForm.amount),
                      note: savingsForm.note || null,
                    },
                  });
                }}
              >
                <label className="text-[0.72rem] text-white/40">
                  Change
                  <select
                    value={savingsForm.entry_type}
                    onChange={(event) => setSavingsForm((previous) => ({ ...previous, entry_type: event.target.value }))}
                    className="mt-1 w-full rounded-xl border border-white/[0.12] bg-white/[0.06] px-3 py-2.5 text-sm text-white/80"
                  >
                    <option value="deposit">Add savings</option>
                    <option value="withdrawal">Record withdrawal</option>
                  </select>
                </label>
                <GlassInput
                  label="Amount"
                  type="number"
                  min={0.01}
                  step="0.01"
                  value={savingsForm.amount}
                  onChange={(event) => setSavingsForm((previous) => ({ ...previous, amount: event.target.value }))}
                  required
                />
                <GlassInput
                  label="Date"
                  type="date"
                  value={savingsForm.contribution_date}
                  onChange={(event) => setSavingsForm((previous) => ({ ...previous, contribution_date: event.target.value }))}
                  required
                />
                <GlassInput
                  label="Note (optional)"
                  value={savingsForm.note}
                  onChange={(event) => setSavingsForm((previous) => ({ ...previous, note: event.target.value }))}
                />
                <GlassButton type="submit" className="sm:col-span-2 justify-center" disabled={contributionMutation.isPending}>
                  {contributionMutation.isPending ? 'Saving…' : 'Save change'}
                </GlassButton>
              </form>
              <div className="mt-6">
                <h4 className="mb-2 flex items-center gap-1.5 text-[0.7rem] uppercase tracking-wider text-white/35">
                  <History size={13} /> Contribution history
                </h4>
                {contributions.length === 0 ? (
                  <p className="rounded-xl bg-white/[0.03] p-3 text-sm text-white/30">No savings entries yet.</p>
                ) : (
                  <div className="divide-y divide-white/[0.05] rounded-xl border border-white/[0.08]">
                    {contributions.map((entry) => (
                      <div key={entry.id} className={`flex items-start justify-between gap-3 p-3 ${entry.is_voided ? 'opacity-40' : ''}`}>
                        <div>
                          <p className={`text-sm ${entry.amount >= 0 ? 'text-emerald-300/80' : 'text-amber-300/80'}`}>
                            {entry.amount >= 0 ? '+' : '−'}{formatINR(Math.abs(entry.amount))}
                          </p>
                          <p className="text-[0.65rem] text-white/30">
                            {format(new Date(`${entry.contribution_date}T00:00:00`), 'dd MMM yyyy')} · {entry.source_type.replaceAll('_', ' ')}
                          </p>
                          {entry.note && <p className="mt-1 text-[0.68rem] text-white/35">{entry.note}</p>}
                          {entry.is_voided && <p className="mt-1 text-[0.65rem] text-rose-300/60">Voided: {entry.void_reason}</p>}
                        </div>
                        {!entry.is_voided && (
                          <button
                            type="button"
                            onClick={() => voidContributionMutation.mutate({
                              goalId: savingsGoal.id,
                              contributionId: entry.id,
                            })}
                            className="text-[0.65rem] text-white/25 hover:text-rose-300/70"
                          >
                            Void
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* FD/RD contribution review */}
      <AnimatePresence>
        {suggestionsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="relative max-h-[88vh] w-full max-w-xl overflow-y-auto rounded-[24px] border border-amber-300/[0.18] bg-[#0d2040]/95 p-6 shadow-[0_16px_64px_rgba(0,0,0,0.3)] backdrop-blur-[32px] mx-4"
              role="dialog"
              aria-modal="true"
              aria-labelledby="deposit-review-title"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 id="deposit-review-title" className="flex items-center gap-2 text-white/90 text-[1.1rem]">
                    <AlertTriangle size={16} className="text-amber-300/80" /> Review detected deposits
                  </h3>
                  <p className="mt-1 text-[0.72rem] text-white/35">Nothing changes a goal until you confirm it.</p>
                </div>
                <button onClick={() => setSuggestionsOpen(false)} className="text-white/30 hover:text-white/60" aria-label="Close deposit review">
                  <X size={18} />
                </button>
              </div>
              <div className="mt-5 space-y-3">
                {suggestions.length === 0 ? (
                  <p className="rounded-xl bg-white/[0.03] p-4 text-sm text-white/35">No FD or RD contributions need review.</p>
                ) : suggestions.map((suggestion) => (
                  <div key={suggestion.id} className="rounded-2xl border border-white/[0.09] bg-white/[0.04] p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm text-white/75">{suggestion.merchant || `${suggestion.deposit_type.toUpperCase()} deposit`}</p>
                        <p className="mt-1 text-[0.68rem] text-white/30">{suggestion.transaction_date} · {Math.round(suggestion.confidence * 100)}% confidence</p>
                        <p className="mt-1 text-[0.68rem] text-white/35">{suggestion.evidence}</p>
                      </div>
                      <p className="text-sm text-emerald-300/80">{formatINR(suggestion.amount)}</p>
                    </div>
                    <p className="mt-3 text-[0.67rem] text-white/35">Assign this confirmed debit to:</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {goals.map((goal) => (
                        <button
                          key={goal.id}
                          type="button"
                          disabled={suggestionMutation.isPending}
                          onClick={() => suggestionMutation.mutate({ suggestionId: suggestion.id, goalId: goal.id })}
                          className={`rounded-full border px-3 py-1 text-[0.68rem] ${
                            suggestion.goal_id === goal.id
                              ? 'border-amber-300/30 bg-amber-300/10 text-amber-200/80'
                              : 'border-white/[0.1] text-white/45 hover:bg-white/[0.05]'
                          }`}
                        >
                          {goal.name}
                        </button>
                      ))}
                      <button
                        type="button"
                        disabled={suggestionMutation.isPending}
                        onClick={() => suggestionMutation.mutate({ suggestionId: suggestion.id, goalId: null })}
                        className="rounded-full border border-white/[0.1] px-3 py-1 text-[0.68rem] text-white/45 hover:bg-white/[0.05]"
                      >
                        None
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Goal Modal */}
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
                <h3 className="text-white/90 text-[1.1rem]" style={{ fontWeight: 400 }}>New Goal</h3>
                <button onClick={() => setAddOpen(false)} className="text-white/30 hover:text-white/60"><X size={18} /></button>
              </div>
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  createMutation.mutate({
                    name: form.name,
                    target_amount: parseFloat(form.target_amount),
                    current_saved: parseFloat(form.current_saved || '0'),
                    deadline_date: form.deadline_date,
                    annual_return_rate: parseFloat(form.annual_return_rate || '0') / 100,
                  });
                }}
              >
                <GlassInput
                  label="Goal Name"
                  placeholder="e.g. Emergency Fund"
                  value={form.name}
                  onChange={(e) => setForm(p => ({ ...p, name: e.target.value }))}
                  required
                />
                <GlassInput
                  label="Target Amount"
                  type="number"
                  placeholder="100000"
                  value={form.target_amount}
                  onChange={(e) => setForm(p => ({ ...p, target_amount: e.target.value }))}
                  required
                  min={1}
                />
                <GlassInput
                  label="Already Saved (optional)"
                  type="number"
                  placeholder="0"
                  value={form.current_saved}
                  onChange={(e) => setForm(p => ({ ...p, current_saved: e.target.value }))}
                  min={0}
                  step="0.01"
                />
                <GlassInput
                  label="Expected Annual Return % (optional)"
                  type="number"
                  placeholder="0"
                  value={form.annual_return_rate}
                  onChange={(e) => setForm(p => ({ ...p, annual_return_rate: e.target.value }))}
                  min={0}
                  max={50}
                  step="0.1"
                />
                <GlassInput
                  label="Deadline"
                  type="date"
                  value={form.deadline_date}
                  onChange={(e) => setForm(p => ({ ...p, deadline_date: e.target.value }))}
                  required
                  min={MIN_GOAL_DATE}
                />
                <GlassButton type="submit" className="w-full justify-center" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Creating...' : 'Create Goal'}
                </GlassButton>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
