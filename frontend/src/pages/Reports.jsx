import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { format, subMonths } from 'date-fns';
import {
  FileText, Download, ChevronLeft, ChevronRight, TrendingDown, TrendingUp,
  PiggyBank, Sparkles, FileSpreadsheet, AlertTriangle, CheckCircle2,
  Info, Lightbulb, CalendarRange, ShieldCheck, Repeat2, KeyRound, X
} from 'lucide-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Legend
} from 'recharts';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  fetchReportSummary, fetchReportDetailed, generateReportInsights,
  downloadMonthlyReportPDF, downloadCSV, fetchLicenseStatus, downloadFinancialYearPack,
  fetchLLMConfig,
  updateReportSavingsTarget,
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
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [contentReady, setContentReady] = useState(false);
  const [aiReportData, setAIReportData] = useState(null);
  const now = new Date();
  const [fyStart, setFyStart] = useState(now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1);
  const [taxPackOpen, setTaxPackOpen] = useState(false);
  const [taxPackPassphrase, setTaxPackPassphrase] = useState('');
  const [taxPackConfirmation, setTaxPackConfirmation] = useState('');
  const taxPackPassphraseRef = useRef(null);
  const taxPackDialogRef = useRef(null);
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
  const { data: llmConfig, isLoading: llmLoading } = useQuery({
    queryKey: ['llmConfig'],
    queryFn: fetchLLMConfig,
    staleTime: 60 * 1000,
  });
  const insightsEnabled = license?.features?.includes('advanced_reports') === true;
  const llmConnected = Boolean(llmConfig?.is_active);
  const insightsMutation = useMutation({
    mutationFn: requestedMonth => generateReportInsights(requestedMonth),
    onSuccess: data => setAIReportData(data),
  });
  const targetMutation = useMutation({
    mutationFn: targetPercent => updateReportSavingsTarget(targetPercent),
    onSuccess: async () => {
      setAIReportData(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['reportSummary'] }),
        queryClient.invalidateQueries({ queryKey: ['reportDetailed'] }),
      ]);
    },
  });
  const taxPackMutation = useMutation({
    mutationFn: ({ startYear, passphrase }) => downloadFinancialYearPack(startYear, passphrase),
    onSuccess: () => {
      setTaxPackOpen(false);
      setTaxPackPassphrase('');
      setTaxPackConfirmation('');
    },
  });

  const insightsData = aiReportData?.month === month ? aiReportData : null;
  const insightsLoading = insightsMutation.isPending;
  const insights = insightsData?.insights;
  const comparison = detailed?.category_comparison || [];

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setContentReady(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!taxPackOpen) return undefined;
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const frame = window.requestAnimationFrame(() => taxPackPassphraseRef.current?.focus());
    const handleKeyDown = event => {
      if (event.key === 'Escape' && !taxPackMutation.isPending) {
        setTaxPackOpen(false);
        setTaxPackPassphrase('');
        setTaxPackConfirmation('');
      }
      if (event.key === 'Tab') {
        const focusable = [...(taxPackDialogRef.current?.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) || [])];
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [taxPackOpen, taxPackMutation.isPending]);

  const taxPackPassphraseValid = taxPackPassphrase.length >= 12
    && taxPackPassphrase.length <= 128
    && taxPackPassphrase === taxPackConfirmation;
  const closeTaxPackDialog = () => {
    if (taxPackMutation.isPending) return;
    setTaxPackOpen(false);
    setTaxPackPassphrase('');
    setTaxPackConfirmation('');
  };

  return (
    <div>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Reports</h1>
          <p className="text-white/30 text-[0.8rem]">Deterministic reports with optional, consented AI analysis</p>
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
      <section className="mb-6 grid gap-4 rounded-[24px] border border-white/[0.14] bg-gradient-to-br from-white/[0.09] to-white/[0.045] p-5 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <p className="text-[#54E1D0]/60 text-[0.66rem] uppercase tracking-[0.16em]">Your financial report</p>
          <h2 className="mt-2 text-white/90 text-2xl font-light">{monthLabel}</h2>
          <p className="mt-2 max-w-xl text-white/35 text-sm">
            Here is how your recorded money moved this month. Every total below comes from included transactions.
          </p>
        </div>
        <div className="min-w-[230px] rounded-2xl border border-white/[0.1] bg-black/10 p-4">
          <div className="flex items-center gap-3">
            <div className="grid h-14 w-14 place-items-center rounded-full border-[5px] border-[#17C3B2]/45 bg-[#17C3B2]/[0.08] text-white/85">
              <ShieldCheck size={22} />
            </div>
            <div>
              <p className="text-white/35 text-[0.68rem]">Savings target progress</p>
              <p className="mt-0.5 text-2xl font-light text-[#54E1D0]">
                {summary?.financial_health_score ?? '--'}
                {summary?.financial_health_score != null && (
                  <span className="text-xs text-white/25">/100</span>
                )}
              </p>
              <p className="text-white/45 text-xs">{summary?.financial_health_label}</p>
            </div>
          </div>
          <form
            className="mt-3 flex items-end gap-2"
            onSubmit={event => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              const value = Number(form.get('targetPercent'));
              if (Number.isFinite(value)) targetMutation.mutate(value);
            }}
          >
            <label className="min-w-0 flex-1 text-[0.62rem] text-white/30">
              Your monthly target
              <span className="mt-1 flex min-h-9 items-center rounded-lg border border-white/[0.1] bg-black/10 px-2">
                <input
                  type="number"
                  name="targetPercent"
                  min="1"
                  max="80"
                  step="0.1"
                  key={summary?.savings_target_percent ?? 20}
                  defaultValue={summary?.savings_target_percent ?? 20}
                  className="w-full bg-transparent text-xs text-white/65 outline-none"
                  aria-label="Monthly savings target percentage"
                />
                <span className="text-white/25">%</span>
              </span>
            </label>
            <button
              type="submit"
              disabled={targetMutation.isPending}
              className="min-h-9 rounded-lg border border-[#54E1D0]/20 bg-[#17C3B2]/10 px-3 text-[0.65rem] text-[#54E1D0]/80 disabled:opacity-40"
            >
              {targetMutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </form>
          {targetMutation.isError && (
            <p className="mt-1 text-[0.62rem] text-rose-200/70">
              {targetMutation.error?.message || 'Use a target between 1% and 80%.'}
            </p>
          )}
          <p className="mt-3 text-white/22 text-[0.62rem] leading-relaxed">{summary?.financial_health_caveat}</p>
        </div>
      </section>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Money in" value={summaryLoading ? '--' : formatINR(summary?.total_income)} icon={TrendingUp} color="text-emerald-400" delay={0} />
        <StatCard title="Money out" value={summaryLoading ? '--' : formatINR(summary?.total_spend)} icon={TrendingDown} color="text-rose-400" delay={0.05} />
        <StatCard title="Money left" value={summaryLoading ? '--' : formatINR((summary?.total_income || 0) - (summary?.total_spend || 0))} icon={PiggyBank} color={(summary?.total_income || 0) >= (summary?.total_spend || 0) ? 'text-emerald-400' : 'text-rose-400'} delay={0.1} />
        <StatCard title="Regular monthly costs" value={summaryLoading ? '--' : formatINR(summary?.recurring_total)} icon={Repeat2} color="text-violet-300" delay={0.15} />
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
              {insights.source === 'llm'
                ? `${insightsData?.llm?.provider || 'AI'} · ${insightsData?.llm?.model || 'connected model'}`
                : 'Verified data notes'}
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
        ) : !llmLoading && !llmConnected ? (
          <div className="rounded-xl bg-white/[0.04] border border-white/[0.08] p-5 text-center">
            <p className="text-white/60 text-sm">Connect an AI to create the detailed written analysis.</p>
            <p className="mx-auto mt-1 max-w-xl text-white/30 text-xs">
              GODFIN gives the AI a verified monthly summary. The AI adds explanations and suggestions; it never changes the totals.
            </p>
            <a href="/settings" className="inline-flex mt-3 text-xs text-[#54E1D0]/80 hover:text-[#54E1D0]">
              Open AI settings
            </a>
          </div>
        ) : insightsLoading || llmLoading ? (
          <div className="space-y-3">
            <div className="h-4 bg-white/5 rounded animate-pulse w-3/4" />
            <div className="h-4 bg-white/5 rounded animate-pulse w-1/2" />
            <div className="h-4 bg-white/5 rounded animate-pulse w-2/3" />
          </div>
        ) : insightsMutation.isError && !insights ? (
          <div className="rounded-xl bg-rose-400/[0.05] border border-rose-400/[0.14] p-5 text-center">
            <p className="text-rose-200/75 text-sm">The connected AI could not create this report.</p>
            <p className="mx-auto mt-1 max-w-xl text-white/30 text-xs">
              {insightsMutation.error?.message || 'Check the model connection and try again.'}
            </p>
            <GlassButton
              variant="secondary"
              className="mt-4"
              onClick={() => insightsMutation.mutate(month)}
            >
              Try again
            </GlassButton>
          </div>
        ) : !insights ? (
          <div className="rounded-xl bg-cyan-400/[0.04] border border-cyan-300/[0.12] p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck size={18} className="mt-0.5 shrink-0 text-[#54E1D0]/80" />
              <div>
                <p className="text-white/70 text-sm">Generate an AI explanation only when you choose</p>
                <p className="mt-1 text-white/35 text-xs leading-relaxed">
                  Provider: {llmConfig?.provider || 'connected AI'} · {llmConfig?.model || 'configured model'}.
                  {llmConfig?.is_local
                    ? ' The report data stays on this computer and is processed by your local model.'
                    : ' GODFIN sends redacted amount bands, ratios, counts, categories, and trend direction. It removes merchant names, account/card details, payment addresses, phone numbers, references, exact dates and amounts, raw descriptions, transaction IDs, your PIN, license key, and Gmail credentials.'}
                </p>
                <p className="mt-2 text-white/25 text-xs leading-relaxed">
                  The AI adds plain-language commentary only. Verified local calculations remain authoritative.
                </p>
                <GlassButton
                  variant="secondary"
                  className="mt-4"
                  icon={<Sparkles size={14} />}
                  onClick={() => insightsMutation.mutate(month)}
                >
                  I agree — generate AI insights
                </GlassButton>
              </div>
            </div>
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
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-1" style={{ fontWeight: 500 }}>Completed-Month Category Comparison</h2>
          <p className="mb-4 text-[0.62rem] text-white/22">
            {detailed?.category_comparison_caveat || 'Waiting for comparable completed months.'}
          </p>
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
                  <Bar dataKey="average" name="Recorded-month avg" fill="rgba(255,255,255,0.1)" radius={[0, 4, 4, 0]} />
                  <Legend wrapperStyle={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)' }} iconSize={8} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </motion.div>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <section className="rounded-[20px] border border-white/[0.14] bg-white/[0.06] p-5">
          <h2 className="text-white/55 text-sm font-medium">Where your income came from</h2>
          {!detailed?.income_breakdown?.length ? (
            <p className="py-8 text-center text-sm text-white/25">No income sources recorded for this month.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {detailed.income_breakdown.slice(0, 7).map((item, index) => {
                const percentage = summary?.total_income > 0 ? (item.amount / summary.total_income) * 100 : 0;
                return (
                  <div key={`${item.source}-${index}`}>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="truncate text-white/45">{item.source}</span>
                      <span className="text-white/65 tabular-nums">{formatINR(item.amount)} · {percentage.toFixed(1)}%</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className="h-full rounded-full bg-gradient-to-r from-emerald-400/65 to-[#54E1D0]/65" style={{ width: `${Math.min(100, percentage)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
        <section className="rounded-[20px] border border-white/[0.14] bg-white/[0.06] p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-white/55 text-sm font-medium">Regular payments</h2>
            <span className="text-white/45 text-xs">{formatINR(summary?.recurring_total || 0)} / month</span>
          </div>
          {!detailed?.recurring_list?.length ? (
            <p className="py-8 text-center text-sm text-white/25">No confirmed repeating payments for this month.</p>
          ) : (
            <div className="mt-4 divide-y divide-white/[0.06]">
              {detailed.recurring_list.slice(0, 7).map((item, index) => (
                <div key={`${item.merchant}-${index}`} className="flex items-center justify-between gap-3 py-2.5 text-xs">
                  <div className="min-w-0">
                    <p className="truncate text-white/55">{item.merchant || 'Unknown payment'}</p>
                    <p className="mt-0.5 text-white/22">{item.category || 'Uncategorised'} · {item.frequency}</p>
                  </div>
                  <span className="shrink-0 text-white/65 tabular-nums">{formatINR(item.amount)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
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
          <GlassButton
            variant="secondary"
            icon={<Download size={14} />}
            onClick={() => downloadMonthlyReportPDF('detailed', month)}
            disabled={!llmConnected}
            title={llmConnected ? 'Generate and download the report with connected-AI commentary' : 'Connect an AI in Settings first'}
          >
            Generate &amp; Download AI PDF
          </GlassButton>
          <GlassButton variant="secondary" icon={<FileSpreadsheet size={14} />} onClick={() => downloadCSV(month)}>Export CSV</GlassButton>
        </div>
        {!llmConnected && !llmLoading && (
          <p className="mt-2 text-amber-200/45 text-xs">
            Connect an AI in Settings to create the detailed report. Summary PDF and data exports remain available.
          </p>
        )}
        {llmConnected && (
          <p className="mt-2 max-w-3xl text-white/25 text-xs leading-relaxed">
            Clicking the AI PDF button sends the same disclosed monthly aggregates shown above to
            {` ${llmConfig?.provider || 'your connected provider'}`} for this one report. Standard PDF and CSV exports never call an AI.
          </p>
        )}
        <div className="mt-5 pt-5 border-t border-white/[0.07]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-white/55 text-sm">
                <CalendarRange size={15} /> Export for CA
              </div>
              <p className="mt-1 text-white/25 text-xs">AES-256 encrypted ZIP with a multi-sheet workbook, privacy-minimized CSV, manifest, reconciliation summary, and AY filing guide.</p>
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
                onClick={() => setTaxPackOpen(true)}
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

      {taxPackOpen && (
        <>
          <div
            aria-hidden="true"
            className="fixed inset-0 z-50 cursor-default bg-black/65 backdrop-blur-sm"
            onClick={closeTaxPackDialog}
          />
          <section
            ref={taxPackDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="tax-pack-title"
            aria-describedby="tax-pack-description"
            className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-[24px] border border-white/[0.14] bg-[#102342] p-6 shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-cyan-300/15 bg-cyan-300/[0.08] text-cyan-200/75">
                  <KeyRound size={18} />
                </span>
                <div>
                  <h2 id="tax-pack-title" className="text-lg font-medium text-white/90">Protect your CA tax pack</h2>
                  <p id="tax-pack-description" className="mt-1 text-sm leading-relaxed text-white/45">
                    This file contains sensitive dates, amounts, and tax-review details. GODFIN encrypts every file with AES-256 and never stores this passphrase.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={closeTaxPackDialog}
                disabled={taxPackMutation.isPending}
                aria-label="Close protected tax pack dialog"
                className="rounded-lg p-1 text-white/30 hover:text-white/65 disabled:opacity-30"
              >
                <X size={18} />
              </button>
            </div>

            <form
              className="mt-5 space-y-4"
              onSubmit={event => {
                event.preventDefault();
                if (!taxPackPassphraseValid) return;
                taxPackMutation.mutate({
                  startYear: fyStart,
                  passphrase: taxPackPassphrase,
                });
              }}
            >
              <label className="block text-sm text-white/60">
                Archive passphrase
                <input
                  ref={taxPackPassphraseRef}
                  type="password"
                  value={taxPackPassphrase}
                  onChange={event => setTaxPackPassphrase(event.target.value)}
                  minLength={12}
                  maxLength={128}
                  autoComplete="new-password"
                  spellCheck="false"
                  className="mt-1.5 w-full rounded-xl border border-white/[0.13] bg-white/[0.06] px-3 py-2.5 text-white/85 outline-none focus:border-cyan-300/40"
                />
              </label>
              <label className="block text-sm text-white/60">
                Confirm archive passphrase
                <input
                  type="password"
                  value={taxPackConfirmation}
                  onChange={event => setTaxPackConfirmation(event.target.value)}
                  minLength={12}
                  maxLength={128}
                  autoComplete="new-password"
                  spellCheck="false"
                  className="mt-1.5 w-full rounded-xl border border-white/[0.13] bg-white/[0.06] px-3 py-2.5 text-white/85 outline-none focus:border-cyan-300/40"
                />
              </label>
              <div className="rounded-xl border border-amber-300/15 bg-amber-300/[0.06] p-3 text-xs leading-relaxed text-amber-100/55">
                Use at least 12 characters—not your GODFIN PIN. Send the ZIP and passphrase to your CA through different channels. If you forget it, GODFIN cannot recover it. Some built-in archive apps may require an AES-capable extractor.
              </div>
              {taxPackConfirmation && taxPackPassphrase !== taxPackConfirmation && (
                <p role="alert" className="text-xs text-rose-300/75">The two passphrases do not match.</p>
              )}
              <div className="flex justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={closeTaxPackDialog}
                  disabled={taxPackMutation.isPending}
                  className="min-h-11 px-4 text-sm text-white/50 hover:text-white/80 disabled:opacity-30"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!taxPackPassphraseValid || taxPackMutation.isPending}
                  className="min-h-11 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.12] px-4 text-sm text-cyan-100/80 disabled:opacity-35"
                >
                  {taxPackMutation.isPending ? 'Encrypting locally…' : 'Encrypt and download'}
                </button>
              </div>
            </form>
          </section>
        </>
      )}
    </div>
  );
}
