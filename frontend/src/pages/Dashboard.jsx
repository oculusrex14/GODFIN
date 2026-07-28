import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { format } from 'date-fns';
import {
  TrendingDown, TrendingUp, PiggyBank, AlertCircle, Activity, Inbox, Shield,
  Eye, EyeOff, Wallet, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { Link } from '../router';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import {
  fetchDashboardStats,
  fetchDashboardMonths,
  fetchTransactions,
  fetchCategoryBreakdown,
  fetchSpendingTrend,
  fetchReviewStats,
  fetchIngestionStatus,
  fetchSchedulerStatus,
  fetchAuditSessions,
} from '../api/client';
import { StatCard } from '../components/StatCard';
import { GlassSelect } from '../components/GlassSelect';

function formatINR(amount) {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

// Compact INR formatter for axis ticks (shows ₹ symbol)
function formatINRAbbreviated(v) {
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(1)}Cr`;
  if (v >= 100000) return `₹${(v / 100000).toFixed(1)}L`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(0)}k`;
  return `₹${v}`;
}

const CHART_COLORS = [
  '#34d399', '#60a5fa', '#f472b6', '#fbbf24',
  '#a78bfa', '#fb923c', '#2dd4bf', '#f87171',
  '#818cf8', '#4ade80', '#e879f9', '#38bdf8',
];

const PERIOD_OPTIONS = [
  { value: 'full', label: 'Full Month' },
  { value: 'week_1', label: 'Week 1' },
  { value: 'week_2', label: 'Week 2' },
  { value: 'week_3', label: 'Week 3' },
  { value: 'week_4', label: 'Week 4' },
  { value: 'first_half', label: 'First Half' },
  { value: 'second_half', label: 'Second Half' },
];

const tooltipStyle = {
  background: 'rgba(15,30,60,0.9)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  fontSize: '12px',
  color: '#ffffff',
  backdropFilter: 'blur(12px)',
};

export default function Dashboard() {
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth();

  const [selectedMonthYear, setSelectedMonthYear] = useState(
    `${currentYear}-${(currentMonth + 1).toString().padStart(2, '0')}`
  );
  const [period, setPeriod] = useState('full');
  const [showBalance, setShowBalance] = useState(false);

  const { data: monthData } = useQuery({
    queryKey: ['dashboardMonths'],
    queryFn: fetchDashboardMonths,
    staleTime: 60_000,
  });

  const availableMonths = monthData?.months || [selectedMonthYear];
  const effectiveMonth = availableMonths.includes(selectedMonthYear)
    ? selectedMonthYear
    : availableMonths[0];
  const selectedYear = Number(effectiveMonth.slice(0, 4));
  const availableYears = [...new Set(availableMonths.map((month) => Number(month.slice(0, 4))))];
  const yearIndex = availableYears.indexOf(selectedYear);
  const monthYearOptions = availableMonths
    .filter((month) => Number(month.slice(0, 4)) === selectedYear)
    .map((month) => ({
      value: month,
      label: format(new Date(`${month}-01T00:00:00`), 'MMMM yyyy'),
    }));

  function navigateYear(direction) {
    const nextYear = availableYears[yearIndex + direction];
    const nextMonth = availableMonths.find(
      (month) => Number(month.slice(0, 4)) === nextYear,
    );
    if (nextMonth) setSelectedMonthYear(nextMonth);
  }

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboardStats', effectiveMonth, period],
    queryFn: () => fetchDashboardStats(effectiveMonth, period),
  });

  const { data: recentTxns } = useQuery({
    queryKey: ['transactions', { page: 1, page_size: 5, sort_by: 'date', sort_order: 'desc' }],
    queryFn: () => fetchTransactions({ page: 1, page_size: 5, sort_by: 'date', sort_order: 'desc' }),
  });

  const { data: categoryData } = useQuery({
    queryKey: ['categoryBreakdown', effectiveMonth, period],
    queryFn: () => fetchCategoryBreakdown(effectiveMonth, period),
  });

  const { data: trendData } = useQuery({
    queryKey: ['spendingTrend', effectiveMonth],
    queryFn: () => fetchSpendingTrend(6, effectiveMonth),
  });

  const { data: reviewStats } = useQuery({
    queryKey: ['reviewStats'],
    queryFn: fetchReviewStats,
  });

  const { data: ingestionStatus } = useQuery({
    queryKey: ['ingestionStatus'],
    queryFn: fetchIngestionStatus,
  });

  useQuery({
    queryKey: ['schedulerStatus'],
    queryFn: fetchSchedulerStatus,
    enabled: ingestionStatus?.gmail_connected,
    staleTime: 60000,
  });

  const { data: auditSessions } = useQuery({
    queryKey: ['auditSessions'],
    queryFn: fetchAuditSessions,
    staleTime: 60_000,
  });

  const draftAudit = auditSessions?.find((s) => s.status === 'draft');

  return (
    <div>
      {/* Draft Audit Banner */}
      {draftAudit && (
        <Link to="/audit">
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 flex items-center gap-3 px-4 py-2.5 bg-amber-400/[0.08] border border-amber-400/[0.15] rounded-[16px] cursor-pointer hover:bg-amber-400/[0.12] transition-colors backdrop-blur-[12px]"
          >
            <Shield className="h-4 w-4 text-amber-400/80 shrink-0" />
            <span className="text-amber-300/80 text-[0.8rem]">
              Draft audit in progress for {
                ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][draftAudit.period_month]
              } {draftAudit.period_year}
            </span>
            <span className="text-amber-500/40 text-[0.7rem] ml-auto">View &rarr;</span>
          </motion.div>
        </Link>
      )}

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
      >
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>
            Dashboard
          </h1>
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={() => navigateYear(1)}
              disabled={yearIndex < 0 || yearIndex >= availableYears.length - 1}
              className="p-2 rounded-[10px] bg-white/[0.05] border border-white/[0.1] text-white/40 hover:text-white/70 disabled:opacity-25"
              aria-label="Previous year"
            >
              <ChevronLeft size={14} />
            </button>
            <GlassSelect value={effectiveMonth} onChange={setSelectedMonthYear} options={monthYearOptions} />
            <button
              onClick={() => navigateYear(-1)}
              disabled={yearIndex <= 0}
              className="p-2 rounded-[10px] bg-white/[0.05] border border-white/[0.1] text-white/40 hover:text-white/70 disabled:opacity-25"
              aria-label="Next year"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
        <GlassSelect value={period} onChange={setPeriod} options={PERIOD_OPTIONS} />
      </motion.div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        {/* Account Balance — custom card with eye toggle */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0, duration: 0.5 }}
          whileHover={{ scale: 1.02, y: -2 }}
          onClick={() => setShowBalance(!showBalance)}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-4 cursor-pointer select-none"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <div className="flex items-center gap-2.5 mb-2">
            <Wallet size={16} className="text-cyan-400" />
            <span className="text-white/40 text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 400 }}>Account Balance</span>
            {showBalance ? (
              <EyeOff size={12} className="text-white/30 ml-auto" />
            ) : (
              <Eye size={12} className="text-white/30 ml-auto" />
            )}
          </div>
          <p className="text-white/90 text-[1.4rem] tracking-tight" style={{ fontWeight: 300 }}>
            {statsLoading ? '--' : showBalance ? formatINR(stats?.account_balance) : 'Tap to reveal'}
          </p>
          {!showBalance && <p className="text-white/30 text-[0.7rem] mt-0.5">Hidden for privacy</p>}
        </motion.div>
        <StatCard
          title="Month Spend"
          value={statsLoading ? '--' : formatINR(stats?.month_spend)}
          icon={TrendingDown}
          color="text-rose-400"
          delay={0.05}
        />
        <StatCard
          title="Income"
          value={statsLoading ? '--' : formatINR(stats?.month_income)}
          icon={TrendingUp}
          color="text-emerald-400"
          delay={0.1}
        />
        <StatCard
          title="Savings Rate"
          value={statsLoading ? '--' : stats?.savings_rate != null ? `${stats.savings_rate.toFixed(1)}%` : '--'}
          icon={PiggyBank}
          color="text-emerald-400"
          delay={0.15}
        />
        <StatCard
          title="Review Queue"
          value={statsLoading ? '--' : stats?.review_queue_count ?? 0}
          subtitle={stats?.review_queue_count ? 'needs categorization' : 'all clear'}
          icon={AlertCircle}
          color={stats?.review_queue_count > 0 ? 'text-amber-400' : 'text-emerald-400'}
          delay={0.2}
        />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {/* Pie Chart */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>
            Category Breakdown
          </h2>
          {!categoryData?.length ? (
            <p className="text-sm text-white/50 text-center py-8">No spending data</p>
          ) : (
            <div className="flex items-center gap-4">
              <div className="w-36 h-36 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <PieChart>
                    <Pie
                      data={categoryData}
                      dataKey="amount"
                      nameKey="category"
                      cx="50%"
                      cy="50%"
                      innerRadius={28}
                      outerRadius={60}
                      paddingAngle={2}
                      stroke="none"
                    >
                      {categoryData.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: '#fff' }} formatter={(v) => formatINR(v)} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-1.5 overflow-hidden">
                {categoryData.slice(0, 6).map((item, i) => (
                  <div key={item.category} className="flex items-center gap-2 text-[0.7rem]">
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }} />
                    <span className="text-white/50 truncate flex-1">{item.category}</span>
                    <span className="text-white/30 tabular-nums">{formatINR(item.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>

        {/* Line Chart */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>
            Spending Trend
          </h2>
          {!trendData?.length ? (
            <p className="text-sm text-white/50 text-center py-8">No trend data</p>
          ) : (
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="label" stroke="rgba(255,255,255,0.2)" fontSize={10} tickLine={false} />
                  <YAxis stroke="rgba(255,255,255,0.2)" fontSize={10} tickLine={false} tickFormatter={formatINRAbbreviated} />
                  <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: '#fff' }} formatter={(v) => formatINR(v)} />
                  <Line type="monotone" dataKey="spend" name="Spend" stroke="#f87171" strokeWidth={2} dot={{ r: 3, fill: '#f87171' }} />
                  <Line type="monotone" dataKey="income" name="Income" stroke="#34d399" strokeWidth={2} dot={{ r: 3, fill: '#34d399' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </motion.div>
      </div>

      {/* Bottom Row */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Recent Transactions */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5 md:col-span-2"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>
            Recent Transactions
          </h2>
          {!recentTxns?.items?.length ? (
            <p className="text-sm text-white/50">No transactions yet</p>
          ) : (
            <div className="space-y-3">
              {recentTxns.items.map((txn) => (
                <div key={txn.id} className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="text-white/80 text-[0.85rem] truncate">{txn.merchant_normalized || txn.merchant_raw}</p>
                    <p className="text-white/25 text-[0.7rem]">
                      {format(new Date(txn.date), 'dd MMM')}
                      {txn.category && ` · ${txn.category}`}
                    </p>
                  </div>
                  <span className={`text-[0.85rem] tabular-nums ml-3 ${txn.type === 'credit' ? 'text-emerald-400/80' : 'text-white/70'}`} style={{ fontWeight: 500 }}>
                    {txn.type === 'credit' ? '+' : '-'}{formatINR(txn.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* System Health */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>
            System Health
          </h2>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Activity className="h-3.5 w-3.5 text-emerald-400/80" />
              <span className="text-white/50 text-[0.8rem]">Gmail</span>
              <span className={`text-[0.7rem] ml-auto px-2.5 py-0.5 rounded-full ${
                ingestionStatus?.gmail_connected
                  ? 'bg-emerald-500/[0.1] text-emerald-400/80 border border-emerald-500/[0.12]'
                  : 'bg-white/[0.05] text-white/40 border border-white/[0.1]'
              }`}>
                {ingestionStatus?.gmail_connected ? 'Connected' : 'Not connected'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Inbox className="h-3.5 w-3.5 text-blue-400/80" />
              <span className="text-white/50 text-[0.8rem]">Last Ingestion</span>
              <span className="text-white/30 text-[0.7rem] ml-auto">
                {ingestionStatus?.last_run ? format(new Date(ingestionStatus.last_run), 'dd MMM HH:mm') : 'Never'}
              </span>
            </div>
            <div className="border-t border-white/[0.06] pt-3 mt-3 space-y-2">
              <div className="flex justify-between text-[0.7rem]">
                <span className="text-white/30">Review queue</span>
                <span className="text-white/60 tabular-nums">{reviewStats?.queue_size ?? 0}</span>
              </div>
              <div className="flex justify-between text-[0.7rem]">
                <span className="text-white/30">Auto-classified</span>
                <span className="text-emerald-400/70 tabular-nums">{reviewStats?.auto_accepted ?? 0}</span>
              </div>
              <div className="flex justify-between text-[0.7rem]">
                <span className="text-white/30">Soft-flagged</span>
                <span className="text-amber-400/70 tabular-nums">{reviewStats?.soft_flagged ?? 0}</span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
