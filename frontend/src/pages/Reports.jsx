import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { format, subMonths } from 'date-fns';
import {
  FileText, Download, ChevronLeft, ChevronRight, TrendingDown, TrendingUp,
  PiggyBank, Hash, Sparkles, FileSpreadsheet, AlertTriangle, CheckCircle2,
  Info, Lightbulb, CalendarRange
} from 'lucide-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Legend
} from 'recharts';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  fetchReportSummary, fetchReportDetailed, fetchReportInsights,
  downloadMonthlyReportPDF, downloadCSV, fetchLicenseStatus, downloadFinancialYearPack
} from '../api/client';
import { websiteUrl } from '../config/website';
import { StatCard } from '../components/StatCard';
import { GlassButton } from '../components/GlassButton';

function formatINR(amount) {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(amount);
}

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

const tooltipStyle = {
  background: 'rgba(15,30,60,0.9)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px', fontSize: '12px', color: '#ffffff',
  backdropFilter: 'blur(12px)',
};

const TONE_STYLES = {
  positive: {
    border: 'border-l-emerald-400/60',
    badge: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/20',
    icon: CheckCircle2,
    text: 'text-emerald-300',
    bg: 'bg-emerald-400/5',
  },
  warning: {
    border: 'border-l-amber-400/60',
    badge: 'bg-amber-400/10 text-amber-300 border-amber-400/20',
    icon: AlertTriangle,
    text: 'text-amber-300',
    bg: 'bg-amber-400/5',
  },
  negative: {
    border: 'border-l-rose-400/60',
    badge: 'bg-rose-400/10 text-rose-300 border-rose-400/20',
    icon: AlertTriangle,
    text: 'text-rose-300',
    bg: 'bg-rose-400/5',
  },
  neutral: {
    border: 'border-l-white/20',
    badge: 'bg-white/5 text-white/50 border-white/10',
    icon: Info,
    text: 'text-white/50',
    bg: 'bg-white/5',
  },
};

function ToneBadge({ tone, label }) {
  const s = TONE_STYLES[tone] || TONE_STYLES.neutral;
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] border ${s.badge}`}>
      <Icon size={10} /> {label || tone}
    </span>
  );
}

function MarkdownCard({ children, className = '' }) {
  return (
    <div className={`prose prose-invert prose-sm max-w-none ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        p: ({ children }) => <p className="text-white/60 text-[0.8rem] leading-relaxed m-0 mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="text-white/80 font-medium">{children}</strong>,
        em: ({ children }) => <em className="text-white/50 italic">{children}</em>,
        ul: ({ children }) => <ul className="list-disc pl-4 space-y-1 my-2">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 space-y-1 my-2">{children}</ol>,
        li: ({ children }) => <li className="text-white/60 text-[0.8rem] leading-relaxed">{children}</li>,
        h1: ({ children }) => <h1 className="text-white/80 text-[1rem] font-medium mt-0 mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-white/70 text-[0.9rem] font-medium mt-3 mb-2">{children}</h2>,
        h3: ({ children }) => <h3 className="text-white/60 text-[0.85rem] font-medium mt-2 mb-1">{children}</h3>,
        blockquote: ({ children }) => <blockquote className="border-l-2 border-white/10 pl-3 my-2 text-white/40 italic">{children}</blockquote>,
        code: ({ children }) => <code className="bg-white/5 text-white/70 px-1 py-0.5 rounded text-[0.75rem]">{children}</code>,
        pre: ({ children }) => <pre className="bg-white/5 p-3 rounded-lg overflow-x-auto my-2">{children}</pre>,
        a: ({ children, href }) => <a href={href} className="text-blue-400 hover:text-blue-300 underline" target="_blank" rel="noreferrer">{children}</a>,
      }}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

export default function Reports() {
  const [month, setMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [contentReady, setContentReady] = useState(false);
  const now = new Date();
  const [fyStart, setFyStart] = useState(now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1);
  const d = new Date(month + '-01');
  const prev = format(subMonths(d, 1), 'yyyy-MM');
  const next = format(new Date(d.getFullYear(), d.getMonth() + 1, 1), 'yyyy-MM');
  const current = format(new Date(), 'yyyy-MM');
  const monthLabel = format(d, 'MMMM yyyy');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['reportSummary', month],
    queryFn: () => fetchReportSummary(month),
  });

  const { data: detailed } = useQuery({
    queryKey: ['reportDetailed', month],
    queryFn: () => fetchReportDetailed(month),
  });

  const { data: license, isLoading: licenseLoading } = useQuery({
    queryKey: ['license'],
    queryFn: fetchLicenseStatus,
    staleTime: 5 * 60 * 1000,
  });
  const insightsEnabled = license?.features?.includes('advanced_reports') === true;
  const { data: insightsData, isLoading: insightsLoading } = useQuery({
    queryKey: ['reportInsights', month],
    queryFn: () => fetchReportInsights(month),
    staleTime: 5 * 60 * 1000,
    enabled: insightsEnabled,
  });

  const insights = insightsData?.insights;
  const comparison = detailed?.category_comparison || [];

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setContentReady(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <div>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Reports</h1>
          <p className="text-white/30 text-[0.8rem]">Monthly financial reports with AI insights & PDF export</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setMonth(prev)} className="text-white/30 hover:text-white/60 transition-colors p-1"><ChevronLeft size={18} /></button>
          <span className="text-white/70 text-[0.85rem] min-w-[130px] text-center" style={{ fontWeight: 400 }}>{monthLabel}</span>
          <button onClick={() => setMonth(next)} disabled={next > current} className="text-white/30 hover:text-white/60 disabled:opacity-30 transition-colors p-1"><ChevronRight size={18} /></button>
        </div>
      </motion.div>

      {!contentReady ? (
        <div
          className="rounded-[20px] bg-white/[0.06] border border-white/[0.12] p-5"
          role="status"
          aria-live="polite"
        >
          <p className="text-white/45 text-sm">Preparing report details…</p>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4" aria-hidden="true">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="h-24 rounded-2xl bg-white/[0.05] animate-pulse" />
            ))}
          </div>
        </div>
      ) : (
        <>
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Total Spend" value={summaryLoading ? '--' : formatINR(summary?.total_spend)} icon={TrendingDown} color="text-rose-400" delay={0} />
        <StatCard title="Income" value={summaryLoading ? '--' : formatINR(summary?.total_income)} icon={TrendingUp} color="text-emerald-400" delay={0.05} />
        <StatCard title="Savings Rate" value={summaryLoading ? '--' : summary?.savings_rate != null ? `${summary.savings_rate.toFixed(1)}%` : '--'} icon={PiggyBank} color={summary?.savings_rate > 20 ? 'text-emerald-400' : 'text-amber-400'} delay={0.1} />
        <StatCard title="Transactions" value={summaryLoading ? '--' : summary?.transaction_count ?? 0} icon={Hash} color="text-blue-400" delay={0.15} />
      </div>

      {/* AI Financial Insights */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}
        className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5 mb-6"
      >
        <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider flex items-center gap-1.5" style={{ fontWeight: 500 }}>
            <Sparkles size={14} className="text-amber-300" /> AI Financial Insights
          </h2>
          {insights?.source && (
            <span className={`text-[0.6rem] px-1.5 py-0.5 rounded border ${insights.source === 'llm' ? 'bg-emerald-400/10 text-emerald-300 border-emerald-400/20' : 'bg-white/5 text-white/30 border-white/10'}`}>
              {insights.source === 'llm' ? 'AI-Powered' : 'Heuristic'}
            </span>
          )}
        </div>

        {licenseLoading ? (
          <div className="space-y-3" aria-label="Checking report access">
            <div className="h-4 bg-white/5 rounded animate-pulse w-3/4" />
            <div className="h-4 bg-white/5 rounded animate-pulse w-1/2" />
          </div>
        ) : !insightsEnabled ? (
          <div className="rounded-xl bg-white/[0.04] border border-white/[0.08] p-4 text-center">
            <p className="text-white/55 text-sm">Advanced insights are available with GODFIN Pro or Max.</p>
            <p className="text-white/30 text-xs mt-1">Your standard reports and local exports remain available.</p>
            <a
              href={websiteUrl('/pricing')}
              target="_blank"
              rel="noreferrer"
              className="inline-flex mt-3 text-xs text-amber-300/80 hover:text-amber-200 transition-colors"
            >
              View license options
            </a>
          </div>
        ) : insightsLoading ? (
          <div className="space-y-3">
            <div className="h-4 bg-white/5 rounded animate-pulse w-3/4" />
            <div className="h-4 bg-white/5 rounded animate-pulse w-1/2" />
            <div className="h-4 bg-white/5 rounded animate-pulse w-2/3" />
          </div>
        ) : !insights?.available && insights?.source === 'none' ? (
          <p className="text-white/30 text-sm text-center py-4">No transactions recorded for this period.</p>
        ) : (
          <div className="space-y-5">
            {/* Executive Summary */}
            {insights?.executive_summary && (
              <div className="rounded-xl bg-gradient-to-r from-white/[0.06] to-transparent border border-white/[0.08] p-4">
                <MarkdownCard>{insights.executive_summary}</MarkdownCard>
              </div>
            )}

            {/* Highlights Grid */}
            {insights?.highlights?.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {insights.highlights.map((h, i) => {
                  const s = TONE_STYLES[h.tone] || TONE_STYLES.neutral;
                  return (
                    <motion.div key={i} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}
                      className={`rounded-lg border border-white/[0.08] p-3 ${s.bg}`}
                    >
                      <p className="text-white/30 text-[0.6rem] uppercase tracking-wider mb-1">{h.label}</p>
                      <p className={`text-[0.85rem] font-medium ${s.text}`}>{h.value}</p>
                      {h.delta && <p className="text-white/25 text-[0.7rem] mt-0.5">{h.delta}</p>}
                    </motion.div>
                  );
                })}
              </div>
            )}

            {/* Sections */}
            {insights?.sections?.length > 0 && (
              <div className="space-y-3">
                {insights.sections.map((sec, i) => {
                  const s = TONE_STYLES[sec.tone] || TONE_STYLES.neutral;
                  return (
                    <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
                      className={`rounded-lg border border-white/[0.08] border-l-[3px] ${s.border} p-4`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="text-white/70 text-[0.8rem] font-medium">{sec.title}</h3>
                        <ToneBadge tone={sec.tone} />
                      </div>
                      <MarkdownCard>{sec.content}</MarkdownCard>
                    </motion.div>
                  );
                })}
              </div>
            )}

            {/* Recommendations */}
            {insights?.recommendations?.length > 0 && (
              <div className="rounded-lg border border-white/[0.08] p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb size={14} className="text-amber-300" />
                  <h3 className="text-white/70 text-[0.8rem] font-medium">Recommendations</h3>
                </div>
                <div className="space-y-2.5">
                  {insights.recommendations.map((rec, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/[0.06] flex items-center justify-center text-white/30 text-[0.65rem] font-medium mt-0.5">
                        {i + 1}
                      </span>
                      <MarkdownCard className="flex-1">{rec}</MarkdownCard>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {/* Pie */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
          role="img" aria-label="Category spending breakdown pie chart"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Category Breakdown</h2>
          {!summary?.all_categories?.length ? (
            <p className="text-sm text-white/30 text-center py-8">No spending data</p>
          ) : (
            <div className="flex items-center gap-4">
              <div className="w-36 h-36 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <PieChart>
                    <Pie data={summary.all_categories} dataKey="amount" nameKey="category" cx="50%" cy="50%" innerRadius={28} outerRadius={60} paddingAngle={2} stroke="none">
                      {summary.all_categories.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: '#fff' }} formatter={(v) => formatINR(v)} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-1.5 overflow-hidden">
                {summary.all_categories.slice(0, 6).map((item, i) => (
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

        {/* Bar Comparison */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Current vs 3-Month Average</h2>
          {!comparison.length ? (
            <p className="text-sm text-white/30 text-center py-8">No comparison data</p>
          ) : (
            <div className="h-48 min-h-[200px] w-full" role="img" aria-label="Category comparison bar chart">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart data={comparison.filter(item => item.current != null && item.average != null).slice(0, 6)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                  <XAxis type="number" stroke="rgba(255,255,255,0.2)" fontSize={10} tickLine={false} tickFormatter={formatINRAbbreviated} />
                  <YAxis type="category" dataKey="category" stroke="rgba(255,255,255,0.2)" fontSize={9} tickLine={false} width={80} />
                  <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: '#fff' }} formatter={(v) => formatINR(v)} />
                  <Bar dataKey="current" name="This Month" fill="#60a5fa" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="average" name="3-Mo Avg" fill="rgba(255,255,255,0.1)" radius={[0, 4, 4, 0]} />
                  <Legend wrapperStyle={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)' }} iconSize={8} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </motion.div>
      </div>

      {/* Elasticity + Top Merchants */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {/* Spending by Type */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Spending by Type</h2>
          {summary?.spending_by_elasticity ? (
            <div className="space-y-3">
              {[
                { label: 'Fixed', val: summary.spending_by_elasticity.fixed, color: 'from-rose-400 to-rose-500' },
                { label: 'Semi-Flexible', val: summary.spending_by_elasticity.semi_flexible, color: 'from-amber-400 to-amber-500' },
                { label: 'Flexible', val: summary.spending_by_elasticity.flexible, color: 'from-emerald-400 to-emerald-500' },
              ].map(({ label, val, color }) => {
                const total = summary.total_spend || 1;
                const pct = (val / total) * 100;
                return (
                  <div key={label}>
                    <div className="flex justify-between text-[0.7rem] mb-1">
                      <span className="text-white/40">{label}</span>
                      <span className="text-white/60 tabular-nums">{formatINR(val)}</span>
                    </div>
                    <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.8, ease: 'easeOut' }}
                        className={`h-full rounded-full bg-gradient-to-r ${color}`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-white/30 text-center py-4">No data</p>
          )}
        </motion.div>

        {/* Top Merchants */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Top Merchants</h2>
          {!detailed?.top_merchants?.length ? (
            <p className="text-sm text-white/30 text-center py-4">No merchant data</p>
          ) : (
            <div className="space-y-2.5">
              {detailed.top_merchants.slice(0, 7).map((m, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-white/15 text-[0.65rem] w-4 tabular-nums">{i + 1}</span>
                    <span className="text-white/50 text-[0.85rem] truncate">{m.merchant || 'Unknown'}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-white/20 text-[0.7rem] tabular-nums">{m.count}x</span>
                    <span className="text-white/60 text-[0.85rem] tabular-nums">{formatINR(m.amount)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      </div>

      {/* Export */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
        className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5"
      >
        <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
        <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4 flex items-center gap-1.5" style={{ fontWeight: 500 }}>
          <FileText size={14} /> Export Reports
        </h2>
        <div className="flex flex-wrap gap-3">
          <GlassButton icon={<Download size={14} />} onClick={() => downloadMonthlyReportPDF('summary', month)}>Summary PDF</GlassButton>
          <GlassButton variant="secondary" icon={<Download size={14} />} onClick={() => downloadMonthlyReportPDF('detailed', month)}>Detailed PDF</GlassButton>
          <GlassButton variant="secondary" icon={<FileSpreadsheet size={14} />} onClick={() => downloadCSV(month)}>Export CSV</GlassButton>
        </div>
        <div className="mt-5 pt-5 border-t border-white/[0.07]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-white/55 text-sm">
                <CalendarRange size={15} /> Export for CA
              </div>
              <p className="mt-1 text-white/25 text-xs">ZIP with a multi-sheet workbook, raw CSV, manifest, reconciliation summary, and AY filing guide.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={fyStart}
                onChange={event => setFyStart(Number(event.target.value))}
                className="min-h-11 rounded-xl bg-white/[0.06] border border-white/[0.12] px-3 text-white/60 text-xs"
                aria-label="Financial year"
              >
                {Array.from({ length: 6 }, (_, index) => {
                  const year = (now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1) - index;
                  return <option key={year} value={year}>FY {year}–{String(year + 1).slice(-2)}</option>;
                })}
              </select>
              <button
                onClick={() => downloadFinancialYearPack(fyStart)}
                disabled={!insightsEnabled}
                className="min-h-11 px-3 rounded-xl bg-cyan-400/[0.12] border border-cyan-300/[0.16] text-cyan-100/70 disabled:opacity-35 text-xs"
              >
                Download CA Tax Pack
              </button>
            </div>
          </div>
          {!insightsEnabled && !licenseLoading && (
            <p className="mt-2 text-amber-200/45 text-xs">FY exports are included with GODFIN Pro and Max.</p>
          )}
        </div>
      </motion.div>
        </>
      )}
    </div>
  );
}
