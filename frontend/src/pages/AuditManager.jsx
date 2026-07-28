import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Lock, Unlock, CheckCircle, XCircle, RotateCcw, Loader2, Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import { useSearchParams } from '../router';
import {
  fetchAuditSessions, fetchMonthStatus, startAudit, finalizeAudit, discardAudit, reopenAudit,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function getMonthGrid(year) {
  const now = new Date();
  const currentMonth = now.getMonth() + 1;
  const months = [];
  for (let month = 1; month <= 12; month++) {
    months.push({
      year,
      month,
      isFuture: year > now.getFullYear() || (
        year === now.getFullYear() && month > currentMonth
      ),
    });
  }
  return months;
}

const STATUS_STYLES = {
  finalized: { bg: 'bg-emerald-400/[0.06] border-emerald-400/[0.15]', text: 'text-emerald-400/70', icon: Lock, label: 'Finalized' },
  draft: { bg: 'bg-amber-400/[0.06] border-amber-400/[0.15]', text: 'text-amber-400/70', icon: Unlock, label: 'Draft' },
  no_audit: { bg: 'bg-white/[0.04] border-white/[0.08]', text: 'text-white/30', icon: Shield, label: 'No Audit' },
};

function MonthCell({ year, month, isFuture, onAction }) {
  const { data, isLoading } = useQuery({
    queryKey: ['monthStatus', year, month],
    queryFn: () => fetchMonthStatus(year, month),
    staleTime: 30_000,
    enabled: !isFuture,
  });

  const status = isFuture ? 'future' : (data?.status || 'no_audit');
  const style = STATUS_STYLES[status] || STATUS_STYLES.no_audit;
  const Icon = isFuture ? Clock : style.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: isFuture ? 0.4 : 1, y: 0 }}
      className={`relative overflow-hidden rounded-[16px] border p-4 cursor-pointer transition-all duration-200 hover:scale-[1.02] ${isFuture ? 'cursor-not-allowed' : ''} ${style.bg}`}
      onClick={() => !isFuture && onAction(year, month, status)}
    >
      <div className="absolute top-0 left-3 right-3 h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      {isLoading && <Loader2 className="absolute top-2 right-2 h-3 w-3 animate-spin text-white/20" />}
      <div className="flex items-center justify-between mb-2">
        <Icon size={14} className={isFuture ? 'text-white/15' : style.text} />
        <span className={`text-[0.55rem] uppercase tracking-wider ${isFuture ? 'text-white/15' : style.text}`} style={{ fontWeight: 500 }}>
          {isFuture ? 'Pending' : style.label}
        </span>
      </div>
      <div className={`text-[0.95rem] ${isFuture ? 'text-white/20' : 'text-white/70'}`} style={{ fontWeight: 400 }}>
        {MONTH_NAMES[month - 1]}
      </div>
      <div className="text-white/15 text-[0.7rem]">{year}</div>
    </motion.div>
  );
}

export default function AuditManager() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedYear = Number(searchParams.get('year'));
  const requestedMonth = Number(searchParams.get('month'));
  const initialYear = requestedYear || new Date().getFullYear();
  const [visibleYear, setVisibleYear] = useState(initialYear);
  const months = getMonthGrid(visibleYear);
  const [selected, setSelected] = useState(
    requestedYear && requestedMonth >= 1 && requestedMonth <= 12
      ? { year: requestedYear, month: requestedMonth, status: 'finalized' }
      : null,
  );
  const [actionError, setActionError] = useState(null);

  const { data: sessions } = useQuery({
    queryKey: ['auditSessions'],
    queryFn: fetchAuditSessions,
    staleTime: 30_000,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['monthStatus'] });
    queryClient.invalidateQueries({ queryKey: ['auditSessions'] });
  };

  const startMutation = useMutation({
    mutationFn: ({ year, month }) => startAudit(year, month),
    onSuccess: () => { invalidateAll(); setSelected(null); setActionError(null); },
    onError: (err) => setActionError(err.message),
  });

  const finalizeMutation = useMutation({
    mutationFn: (id) => finalizeAudit(id),
    onSuccess: () => { invalidateAll(); setSelected(null); setActionError(null); },
    onError: (err) => setActionError(err.message),
  });

  const discardMutation = useMutation({
    mutationFn: (id) => discardAudit(id),
    onSuccess: () => { invalidateAll(); setSelected(null); setActionError(null); },
    onError: (err) => setActionError(err.message),
  });

  const reopenMutation = useMutation({
    mutationFn: (id) => reopenAudit(id),
    onSuccess: () => { invalidateAll(); setSelected(null); setActionError(null); },
    onError: (err) => setActionError(err.message),
  });

  const loading = startMutation.isPending || finalizeMutation.isPending || discardMutation.isPending || reopenMutation.isPending;

  function handleAction(year, month, status) {
    setActionError(null);
    setSelected({ year, month, status });
  }

  const selectedSession = selected && sessions?.find(
    (s) => s.period_year === selected.year && s.period_month === selected.month && (s.status === 'draft' || s.status === 'finalized')
  );

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3 mb-2">
          <Shield className="h-5 w-5 text-emerald-400/70" />
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Audit Manager</h1>
        </div>
        <p className="text-white/30 text-[0.8rem] max-w-xl">
          Lock monthly transactions to preserve financial integrity. Start an audit to review, then finalize to lock.
        </p>
      </motion.div>

      {/* Month Grid */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setVisibleYear((year) => year - 1)}
          className="inline-flex items-center gap-1.5 text-white/35 hover:text-white/70 text-[0.75rem]"
        >
          <ChevronLeft size={14} /> Previous year
        </button>
        <span className="text-white/60 text-[0.9rem] tabular-nums">{visibleYear}</span>
        <button
          onClick={() => setVisibleYear((year) => Math.min(new Date().getFullYear(), year + 1))}
          disabled={visibleYear >= new Date().getFullYear()}
          className="inline-flex items-center gap-1.5 text-white/35 hover:text-white/70 disabled:opacity-25 text-[0.75rem]"
        >
          Next year <ChevronRight size={14} />
        </button>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
        {months.map(({ year, month, isFuture }) => (
          <MonthCell key={`${year}-${month}`} year={year} month={month} isFuture={isFuture} onAction={handleAction} />
        ))}
      </div>

      {/* Action Panel */}
      <AnimatePresence>
        {selected && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-5">
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white/80 text-[1rem]" style={{ fontWeight: 400 }}>
                  {MONTH_NAMES[selected.month - 1]} {selected.year}
                </h3>
                <button onClick={() => { setSelected(null); setActionError(null); }} className="text-white/30 hover:text-white/60 text-[0.8rem]">Close</button>
              </div>

              {actionError && (
                <div className="mb-3 px-3 py-2 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px] text-rose-400/70 text-[0.8rem]">
                  {actionError}
                </div>
              )}

              {selectedSession?.change_summary && (
                <p className="text-white/30 text-[0.8rem] mb-4">{selectedSession.change_summary}</p>
              )}

              <div className="flex flex-wrap gap-3">
                {selected.status === 'no_audit' && (
                  <GlassButton icon={<CheckCircle size={14} />} onClick={() => startMutation.mutate({ year: selected.year, month: selected.month })} disabled={loading}>
                    Start Audit
                  </GlassButton>
                )}
                {selected.status === 'draft' && selectedSession && (
                  <>
                    <GlassButton icon={<Lock size={14} />} onClick={() => finalizeMutation.mutate(selectedSession.id)} disabled={loading}>Finalize</GlassButton>
                    <GlassButton variant="danger" icon={<XCircle size={14} />} onClick={() => discardMutation.mutate(selectedSession.id)} disabled={loading}>Discard</GlassButton>
                  </>
                )}
                {selected.status === 'finalized' && selectedSession && (
                  <GlassButton variant="secondary" icon={<RotateCcw size={14} />} onClick={() => reopenMutation.mutate(selectedSession.id)} disabled={loading}>Reopen</GlassButton>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Recent Sessions */}
      {sessions?.length > 0 && (
        <div>
          <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-3" style={{ fontWeight: 500 }}>Recent Sessions</h2>
          <div className="space-y-2">
            {sessions.slice(0, 10).map((s) => (
              <div key={s.id} className="flex items-center justify-between bg-white/[0.04] rounded-[14px] px-4 py-3 border border-white/[0.06]">
                <div className="flex items-center gap-3">
                  <span className="text-white/70 text-[0.85rem]" style={{ fontWeight: 400 }}>
                    {MONTH_NAMES[s.period_month - 1]} {s.period_year}
                  </span>
                  <span className={`text-[0.65rem] uppercase tracking-wider ${
                    s.status === 'finalized' ? 'text-emerald-400/70' : s.status === 'draft' ? 'text-amber-400/70' : 'text-white/30'
                  }`} style={{ fontWeight: 500 }}>
                    {s.status}
                  </span>
                </div>
                <span className="text-white/20 text-[0.7rem]">
                  {s.finalized_at ? `Finalized ${new Date(s.finalized_at).toLocaleDateString()}` : s.created_at ? `Created ${new Date(s.created_at).toLocaleDateString()}` : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
