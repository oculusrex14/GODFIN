import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronRight, Circle, KeyRound, Mail, Upload, Tags, LayoutDashboard } from 'lucide-react';
import { motion } from 'framer-motion';

import { fetchOnboardingStatus, updateOnboardingStatus } from '../api/client';
import { useLocation } from '../router';

const STEPS = [
  { title: 'Secure GODFIN', description: 'Your local PIN is set and your session is protected.', icon: KeyRound },
  { title: 'Connect Gmail', description: 'Optional: import bank alerts automatically using your own Gmail connection.', icon: Mail },
  { title: 'Upload a statement', description: 'Import one redacted or real local statement to populate your dashboard.', icon: Upload },
  { title: 'Review 10 transactions', description: 'Confirm classifications so GODFIN learns your merchant patterns.', icon: Tags },
  { title: 'Preview your dashboard', description: 'Finish setup and see your private financial overview.', icon: LayoutDashboard },
];

export default function Onboarding() {
  const { navigate } = useLocation();
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ['onboarding'],
    queryFn: fetchOnboardingStatus,
  });
  const updateMutation = useMutation({
    mutationFn: updateOnboardingStatus,
    onSuccess: data => queryClient.setQueryData(['onboarding'], data),
  });
  const step = status?.step || 1;

  async function finish() {
    await updateMutation.mutateAsync({ step: 5, completed: true });
    navigate('/');
  }

  async function advance() {
    if (step >= 5) {
      await finish();
      return;
    }
    await updateMutation.mutateAsync({ step: step + 1 });
  }

  async function openTask(path, targetStep) {
    await updateMutation.mutateAsync({ step: targetStep });
    navigate(path);
  }

  const CurrentIcon = STEPS[step - 1]?.icon || Check;
  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-8">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-3xl rounded-[28px] bg-[#0d2040]/90 backdrop-blur-[32px] border border-white/[0.14] p-5 sm:p-8 shadow-2xl"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-cyan-300/60 text-xs uppercase tracking-[0.18em]">First-run setup</p>
            <h1 className="mt-2 text-white/90 text-2xl sm:text-3xl" style={{ fontWeight: 300 }}>Make GODFIN yours</h1>
            <p className="mt-2 text-white/35 text-sm">Everything here runs against the SQLite database on this device.</p>
          </div>
          <button
            onClick={finish}
            className="min-h-11 px-3 rounded-xl text-white/35 hover:text-white/65 hover:bg-white/[0.05] text-xs"
          >
            Finish setup later
          </button>
        </div>

        <div className="mt-7 grid sm:grid-cols-[220px_1fr] gap-6">
          <ol className="space-y-2">
            {STEPS.map((item, index) => {
              const number = index + 1;
              const complete = number < step;
              const active = number === step;
              return (
                <li key={item.title} className={`flex items-center gap-3 min-h-11 px-3 rounded-xl ${active ? 'bg-white/[0.08]' : ''}`}>
                  {complete ? <Check size={17} className="text-emerald-300" /> : <Circle size={17} className={active ? 'text-cyan-300' : 'text-white/15'} />}
                  <span className={active ? 'text-white/75 text-sm' : 'text-white/30 text-sm'}>{item.title}</span>
                </li>
              );
            })}
          </ol>

          <div className="rounded-[20px] bg-white/[0.05] border border-white/[0.1] p-5 sm:p-6">
            <div className="w-12 h-12 rounded-2xl bg-cyan-400/10 border border-cyan-400/15 grid place-items-center">
              <CurrentIcon className="text-cyan-200/70" size={22} />
            </div>
            <h2 className="mt-4 text-white/80 text-xl">{STEPS[step - 1]?.title}</h2>
            <p className="mt-2 text-white/40 text-sm leading-relaxed">{STEPS[step - 1]?.description}</p>

            {step === 3 && (
              <p className="mt-3 text-xs text-white/30">
                {status?.transaction_count
                  ? `${status.transaction_count} transactions are already available.`
                  : 'No transactions have been imported yet.'}
              </p>
            )}
            {step === 4 && (
              <p className="mt-3 text-xs text-white/30">
                {status?.reviewed_count || 0} of {status?.target_review_count || 10} available transactions reviewed.
              </p>
            )}

            <div className="mt-6 flex flex-wrap gap-2">
              {step === 2 && (
                <button onClick={() => openTask('/settings', 2)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open Gmail settings
                </button>
              )}
              {step === 3 && (
                <button onClick={() => openTask('/upload', 3)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open statement upload
                </button>
              )}
              {step === 4 && (
                <button onClick={() => openTask('/review', 4)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open review queue
                </button>
              )}
              <button
                onClick={advance}
                disabled={updateMutation.isPending}
                className="min-h-11 px-4 rounded-xl bg-white/[0.08] text-white/65 border border-white/[0.12] text-sm flex items-center gap-2"
              >
                {step === 1 ? 'Continue' : step === 5 ? 'Open dashboard' : 'Continue'}
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
