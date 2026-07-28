import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowRightLeft, Check, Clock3, RefreshCw, X } from 'lucide-react';

import {
  decideTransferMatch,
  fetchLicenseStatus,
  fetchTransferMatches,
  scanTransferMatches,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';

function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value || 0);
}

export default function Transfers() {
  const queryClient = useQueryClient();
  const { data: license, isLoading: licenseLoading } = useQuery({
    queryKey: ['license'],
    queryFn: fetchLicenseStatus,
  });
  const enabled = license?.features?.includes('multi_bank') === true;
  const { data: matches = [], isLoading } = useQuery({
    queryKey: ['transferMatches'],
    queryFn: () => fetchTransferMatches(false),
    enabled,
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['transferMatches'] });
    queryClient.invalidateQueries({ queryKey: ['transactions'] });
    queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
    queryClient.invalidateQueries({ queryKey: ['cashFlowCalendar'] });
  };
  const scanMutation = useMutation({
    mutationFn: scanTransferMatches,
    onSuccess: refresh,
  });
  const decisionMutation = useMutation({
    mutationFn: decideTransferMatch,
    onSuccess: refresh,
  });

  if (!licenseLoading && !enabled) {
    return (
      <div>
        <h1 className="text-white/90 text-[1.6rem]" style={{ fontWeight: 300 }}>Transfer Matching</h1>
        <div className="mt-6 rounded-[20px] bg-white/[0.07] border border-white/[0.14] p-8 text-center">
          <ArrowRightLeft className="mx-auto text-white/20" size={34} />
          <p className="mt-3 text-white/60">Transfer matching is available with GODFIN Pro or Max.</p>
          <p className="mt-1 text-white/30 text-sm">Match credit-card payments to bank debits so they are never counted twice.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-white/90 text-[1.6rem]" style={{ fontWeight: 300 }}>Transfer Matching</h1>
          <p className="text-white/30 text-[0.8rem]">Confirm paired movements to prevent double-counting.</p>
        </div>
        <GlassButton
          icon={<RefreshCw size={15} className={scanMutation.isPending ? 'animate-spin' : ''} />}
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
        >
          Scan
        </GlassButton>
      </motion.div>

      {isLoading ? (
        <p className="text-white/30 text-sm">Checking local transactions…</p>
      ) : matches.length === 0 ? (
        <div className="rounded-[20px] bg-white/[0.07] border border-white/[0.14] p-8 text-center">
          <Check className="mx-auto text-emerald-300/50" size={32} />
          <p className="mt-3 text-white/55">No transfer candidates need review.</p>
          <p className="mt-1 text-white/25 text-sm">Run a scan after importing both account statements.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {matches.map(match => (
            <motion.div
              key={match.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-[20px] bg-white/[0.07] border border-white/[0.14] p-4 sm:p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-white/85 text-lg tabular-nums">{money(match.amount)}</div>
                  <div className="text-white/25 text-xs mt-1">{Math.round(match.confidence * 100)}% confidence · {match.date_gap_days} day gap</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => decisionMutation.mutate({ id: match.id, decision: 'confirm' })}
                    className="min-h-11 px-3 rounded-xl bg-emerald-400/10 text-emerald-200/80 border border-emerald-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Check size={14} /> Confirm
                  </button>
                  <button
                    onClick={() => decisionMutation.mutate({ id: match.id, decision: 'snooze', snoozeDays: 7 })}
                    className="min-h-11 px-3 rounded-xl bg-amber-400/10 text-amber-200/80 border border-amber-400/20 text-xs flex items-center gap-1.5"
                  >
                    <Clock3 size={14} /> Snooze
                  </button>
                  <button
                    onClick={() => decisionMutation.mutate({ id: match.id, decision: 'ignore' })}
                    className="min-h-11 px-3 rounded-xl bg-white/[0.04] text-white/40 border border-white/[0.1] text-xs flex items-center gap-1.5"
                  >
                    <X size={14} /> Ignore
                  </button>
                </div>
              </div>
              <div className="mt-4 grid sm:grid-cols-[1fr_auto_1fr] items-center gap-3">
                {[match.debit, match.credit].map((transaction, index) => (
                  <div key={transaction.id} className="rounded-xl bg-black/10 border border-white/[0.07] p-3">
                    <div className="text-white/60 text-sm truncate">{transaction.merchant}</div>
                    <div className="text-white/25 text-xs mt-1">{transaction.account} · {transaction.date}</div>
                    <div className={index === 0 ? 'text-rose-300/70 mt-2 text-sm' : 'text-emerald-300/70 mt-2 text-sm'}>
                      {index === 0 ? 'Debit' : 'Credit'} {money(transaction.amount)}
                    </div>
                  </div>
                )).reduce((items, item, index) => (
                  index === 0 ? [item] : [...items, <ArrowRightLeft key="arrow" className="mx-auto text-white/20" size={18} />, item]
                ), [])}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
