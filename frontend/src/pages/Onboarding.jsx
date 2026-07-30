import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Circle,
  KeyRound,
  LayoutDashboard,
  Mail,
  Tags,
  Upload,
} from 'lucide-react';
import { motion } from 'framer-motion';

import { fetchOnboardingStatus, updateOnboardingStatus } from '../api/client';
import LocalAISetup from '../components/settings/LocalAISetup';
import { useLocation } from '../router';

const STEPS = [
  {
    title: 'Secure GODFIN',
    description: 'Your local PIN is set and your session is protected.',
    icon: KeyRound,
  },
  {
    title: 'Choose how AI works',
    description: 'Use private local AI, connect your own provider, or keep AI off.',
    icon: Bot,
  },
  {
    title: 'Connect Gmail',
    description: 'Optional: import bank alerts automatically using your own Gmail connection.',
    icon: Mail,
  },
  {
    title: 'Upload a statement',
    description: 'Import a local bank statement. The file and extracted transactions stay on this device.',
    icon: Upload,
  },
  {
    title: 'Review transactions',
    description: 'Confirm classifications so GODFIN learns only from corrections you explicitly approve.',
    icon: Tags,
  },
  {
    title: 'Preview your dashboard',
    description: 'Finish setup and see your private financial overview.',
    icon: LayoutDashboard,
  },
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
  const step = Math.min(STEPS.length, Math.max(1, status?.step || 1));

  async function finish() {
    await updateMutation.mutateAsync({
      step: STEPS.length,
      completed: true,
      deferred: false,
    });
    navigate('/');
  }

  async function deferSetup() {
    await updateMutation.mutateAsync({
      step,
      completed: false,
      deferred: true,
    });
    navigate('/');
  }

  async function advance() {
    if (step >= STEPS.length) {
      await finish();
      return;
    }
    await updateMutation.mutateAsync({
      step: step + 1,
      deferred: false,
    });
  }

  async function goBack() {
    if (step <= 1) return;
    await updateMutation.mutateAsync({ step: step - 1, deferred: false });
  }

  async function openTask(path, targetStep) {
    await updateMutation.mutateAsync({ step: targetStep, deferred: false });
    navigate(path);
  }

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'ArrowLeft' && step > 1 && !updateMutation.isPending) {
        event.preventDefault();
        goBack();
      }
      if (
        event.key === 'ArrowRight'
        && step !== 2
        && !updateMutation.isPending
        && !event.target.closest('input, textarea, select, button, a')
      ) {
        event.preventDefault();
        advance();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  const CurrentIcon = STEPS[step - 1]?.icon || Check;
  return (
    <main className="min-h-screen flex items-center justify-center p-4 sm:p-8">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-5xl rounded-[28px] bg-[#0d2040]/90 backdrop-blur-[32px] border border-white/[0.14] p-5 sm:p-8 shadow-2xl"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-cyan-300/60 text-xs uppercase tracking-[0.18em]">First-run setup</p>
            <h1 className="mt-2 text-white/90 text-2xl sm:text-3xl" style={{ fontWeight: 300 }}>Make GODFIN yours</h1>
            <p className="mt-2 text-white/35 text-sm">Your everyday money records stay on this device.</p>
          </div>
          <button
            type="button"
            onClick={deferSetup}
            disabled={updateMutation.isPending}
            className="min-h-11 px-3 rounded-xl text-white/40 hover:text-white/70 hover:bg-white/[0.05] text-xs"
          >
            Finish setup later
          </button>
        </div>

        <div className="mt-7 grid lg:grid-cols-[220px_1fr] gap-6">
          <ol className="space-y-2" aria-label="Setup progress">
            {STEPS.map((item, index) => {
              const number = index + 1;
              const complete = number < step;
              const active = number === step;
              return (
                <li
                  key={item.title}
                  aria-current={active ? 'step' : undefined}
                  className={`flex items-center gap-3 min-h-11 px-3 rounded-xl ${active ? 'bg-white/[0.08]' : ''}`}
                >
                  {complete ? <Check size={17} className="text-emerald-300" /> : <Circle size={17} className={active ? 'text-cyan-300' : 'text-white/15'} />}
                  <span className={active ? 'text-white/75 text-sm' : 'text-white/30 text-sm'}>{item.title}</span>
                </li>
              );
            })}
          </ol>

          <section
            className="rounded-[20px] bg-white/[0.05] border border-white/[0.1] p-5 sm:p-6"
            aria-live="polite"
          >
            <div className="w-12 h-12 rounded-2xl bg-cyan-400/10 border border-cyan-400/15 grid place-items-center">
              <CurrentIcon className="text-cyan-200/70" size={22} />
            </div>
            <h2 className="mt-4 text-white/80 text-xl">{STEPS[step - 1]?.title}</h2>
            <p className="mt-2 text-white/40 text-sm leading-relaxed">{STEPS[step - 1]?.description}</p>

            {step === 2 && (
              <div className="mt-5">
                <LocalAISetup onChoiceComplete={() => undefined} />
              </div>
            )}
            {step === 4 && (
              <p className="mt-3 text-xs text-white/30">
                {status?.transaction_count
                  ? `${status.transaction_count} transactions are already available.`
                  : 'No transactions have been imported yet.'}
              </p>
            )}
            {step === 5 && (
              <p className="mt-3 text-xs text-white/30">
                {status?.reviewed_count || 0} of {status?.target_review_count || 10} available transactions reviewed.
              </p>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={goBack}
                disabled={step <= 1 || updateMutation.isPending}
                className="min-h-11 px-4 rounded-xl text-white/45 border border-white/[0.08] disabled:opacity-30 text-sm flex items-center gap-2"
              >
                <ChevronLeft size={15} />
                Back
              </button>
              {step === 3 && (
                <button type="button" onClick={() => openTask('/settings', 3)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open Gmail settings
                </button>
              )}
              {step === 4 && (
                <button type="button" onClick={() => openTask('/upload', 4)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open statement upload
                </button>
              )}
              {step === 5 && (
                <button type="button" onClick={() => openTask('/review', 5)} className="min-h-11 px-4 rounded-xl bg-cyan-400/10 text-cyan-200/80 border border-cyan-400/20 text-sm">
                  Open review queue
                </button>
              )}
              <button
                type="button"
                onClick={advance}
                disabled={updateMutation.isPending || (step === 2 && !status)}
                className="min-h-11 px-4 rounded-xl bg-white/[0.08] text-white/65 border border-white/[0.12] text-sm flex items-center gap-2"
              >
                {step === STEPS.length ? 'Finish setup' : 'Continue'}
                <ChevronRight size={15} />
              </button>
            </div>
            <p className="mt-4 text-white/20 text-[0.65rem]">
              Keyboard: use Left and Right Arrow outside form fields. You can resume setup from Settings.
            </p>
          </section>
        </div>
      </motion.div>
    </main>
  );
}
