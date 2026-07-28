import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { addDays, format, differenceInDays } from 'date-fns';
import {
  Target, Plus, Trash2, Sparkles, PiggyBank, Gauge, Wallet,
  Repeat, CreditCard, TrendingUp, RefreshCw, X,
} from 'lucide-react';
import {
  fetchGoals, createGoal, deleteGoal, simulateGoal,
  fetchRecurring, detectRecurring,
  fetchFinancialProfile,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';

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

function HealthGauge({ label, value, max = 1, invert = false, icon: Icon }) {
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
        </div>
        <span className={`text-[0.8rem] tabular-nums ${textColor}`} style={{ fontWeight: 500 }}>
          {value != null && !isNaN(value) ? `${(value * 100).toFixed(1)}%` : '--'}
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
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ name: '', target_amount: '', deadline_date: '' });
  const [simResult, setSimResult] = useState(null);
  const [simGoalId, setSimGoalId] = useState(null);

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

  const createMutation = useMutation({
    mutationFn: createGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({ queryKey: ['financialProfile'] });
      setAddOpen(false);
      setForm({ name: '', target_amount: '', deadline_date: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals'] }),
  });

  const detectMutation = useMutation({
    mutationFn: detectRecurring,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recurring'] }),
  });

  const simulateMutation = useMutation({
    mutationFn: simulateGoal,
    onSuccess: (data, goalId) => {
      setSimResult(data);
      setSimGoalId(goalId);
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
            <HealthGauge label="Savings Rate" value={profile.savings_rate} icon={PiggyBank} />
            <HealthGauge label="Impulse Index" value={profile.impulse_index} invert icon={Gauge} />
            <HealthGauge label="Fixed Expense Ratio" value={profile.fixed_expense_ratio} invert icon={Wallet} />
            <HealthGauge label="Recurring Burden" value={profile.recurring_burden} invert icon={Repeat} />
            <HealthGauge label="Subscription Dependency" value={profile.subscription_dependency} invert icon={CreditCard} />
            <HealthGauge label="Lifestyle Inflation" value={profile.lifestyle_inflation} max={2} invert icon={TrendingUp} />
          </div>
        </motion.div>
      )}

      {/* Goals */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="mb-6">
        <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ fontWeight: 500 }}>
          <Target size={14} /> Goals ({goals.length})
        </h2>
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
                      <h3 className="text-white/80 text-[0.9rem]" style={{ fontWeight: 400 }}>{goal.name}</h3>
                      <p className="text-white/25 text-[0.7rem] mt-0.5">
                        {daysLeft} days left · {format(new Date(goal.deadline_date), 'dd MMM yyyy')}
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
                  <button
                    onClick={() => simulateMutation.mutate(goal.id)}
                    disabled={simulateMutation.isPending && simGoalId === goal.id}
                    className="text-cyan-400/50 text-[0.7rem] hover:text-cyan-300/70 transition-colors flex items-center gap-1"
                  >
                    <Sparkles size={12} className={simulateMutation.isPending && simGoalId === goal.id ? 'animate-spin' : ''} />
                    {simulateMutation.isPending && simGoalId === goal.id ? 'Simulating...' : 'Run Simulation'}
                  </button>
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
                    <p className="text-white/70 text-[0.85rem]">{p.merchant}</p>
                    <p className="text-white/25 text-[0.7rem]">
                      {p.frequency} · {p.category || 'Uncategorized'}
                      {p.next_expected && ` · Next: ${format(new Date(p.next_expected), 'dd MMM')}`}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-white/70 text-[0.85rem] tabular-nums">{formatINR(p.avg_amount)}</p>
                    <p className="text-white/20 text-[0.6rem]">{p.times_detected}x detected</p>
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
                  <span className={`text-[0.85rem] px-2.5 py-0.5 rounded-full ${simResult.is_feasible ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                    {simResult.is_feasible ? 'Feasible' : 'Not Feasible'}
                  </span>
                </div>

                {!simResult.is_feasible && simResult.extended_deadline_months && (
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
                    deadline_date: form.deadline_date,
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
