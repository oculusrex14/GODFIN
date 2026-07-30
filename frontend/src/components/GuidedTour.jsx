import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';

import { fetchOnboardingStatus, updateOnboardingStatus } from '../api/client';
import { useLocation } from '../router';

const ACTIVE_KEY = 'godfin:guided-tour-active';
const ACTIVE_EVENT = 'godfin:guided-tour-changed';

const TOUR_STEPS = [
  {
    path: '/',
    title: 'Your money at a glance',
    body: 'The Dashboard is your home screen. It shows what came in, what went out, and anything that still needs your attention.',
    lookFor: 'Start with the four summary cards, then look at the spending chart and recent activity.',
  },
  {
    path: '/transactions',
    title: 'Every money movement',
    body: 'Transactions is the complete list of money entering or leaving your accounts. Search and filters help you find a payment quickly.',
    lookFor: 'Open a row to check its account, category, date, and why GODFIN chose that category.',
  },
  {
    path: '/transfers',
    title: 'Money moved between your accounts',
    body: 'Transfers are separated from spending so moving money from one of your accounts to another does not make your expenses look larger.',
    lookFor: 'Review suggested matches and confirm only the pairs that really belong together.',
  },
  {
    path: '/review',
    title: 'Teach GODFIN carefully',
    body: 'Review shows payments that need a category check. Confirming or correcting one helps GODFIN remember your choice on this computer.',
    lookFor: 'Check the merchant, amount, and suggested category before you confirm.',
  },
  {
    path: '/upload',
    title: 'Bring in a bank statement',
    body: 'Choose the account first, then add a supported statement. GODFIN checks for repeated rows before saving anything.',
    lookFor: 'Read the preview and warnings before you finish an import.',
  },
  {
    path: '/budget',
    title: 'Plan without punishing yourself',
    body: 'Budgets show where you hoped your money would go. Goals track money you have already saved and what remains.',
    lookFor: 'Use Add savings on a goal whenever you move money toward it.',
  },
  {
    path: '/subscriptions',
    title: 'Spot repeating commitments',
    body: 'Subscriptions lists payments that appear to repeat. GODFIN asks you to confirm suggestions instead of silently deciding for you.',
    lookFor: 'Use Re-detect after a new import if a regular payment is missing.',
  },
  {
    path: '/reports',
    title: 'Turn activity into a clear story',
    body: 'Reports brings income, spending, saving, categories, and regular payments together for the month you choose.',
    lookFor: 'Standard totals always come from your verified data. A connected AI can add plain-language commentary.',
  },
  {
    path: '/behavior-insights',
    title: 'Reflect on money habits',
    body: 'These observations help you notice patterns such as small purchases adding up or spending changing near the end of a month.',
    lookFor: 'Treat each card as a question to consider, not as a score or diagnosis.',
  },
  {
    path: '/settings',
    title: 'You remain in control',
    body: 'Settings is where you manage backups, accounts, Gmail, optional AI, your license, and privacy choices.',
    lookFor: 'Open only the section you need. You can restart this tour or read Learn GODFIN at any time.',
  },
];

// The Settings screen starts the tour through this small event bridge.
// eslint-disable-next-line react-refresh/only-export-components
export function activateGuidedTour() {
  window.localStorage.setItem(ACTIVE_KEY, 'true');
  window.dispatchEvent(new Event(ACTIVE_EVENT));
}

function deactivateGuidedTour() {
  window.localStorage.setItem(ACTIVE_KEY, 'false');
  window.dispatchEvent(new Event(ACTIVE_EVENT));
}

export default function GuidedTour() {
  const { pathname, navigate } = useLocation();
  const queryClient = useQueryClient();
  const [active, setActive] = useState(() => window.localStorage.getItem(ACTIVE_KEY) === 'true');
  const { data: status } = useQuery({
    queryKey: ['onboarding'],
    queryFn: fetchOnboardingStatus,
    enabled: active,
  });
  const mutation = useMutation({
    mutationFn: updateOnboardingStatus,
    onSuccess: data => queryClient.setQueryData(['onboarding'], data),
  });
  const stepNumber = Math.min(TOUR_STEPS.length, Math.max(1, status?.tutorial_step || 1));
  const step = useMemo(() => TOUR_STEPS[stepNumber - 1], [stepNumber]);

  useEffect(() => {
    const sync = () => setActive(window.localStorage.getItem(ACTIVE_KEY) === 'true');
    window.addEventListener(ACTIVE_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(ACTIVE_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    if (active && step && pathname !== step.path) navigate(step.path);
  }, [active, navigate, pathname, step]);

  if (!active || !status) return null;

  async function move(nextStep) {
    await mutation.mutateAsync({ tutorial_step: nextStep, tutorial_completed: false });
    navigate(TOUR_STEPS[nextStep - 1].path);
  }

  async function finish() {
    await mutation.mutateAsync({
      tutorial_step: TOUR_STEPS.length,
      tutorial_completed: true,
    });
    deactivateGuidedTour();
  }

  async function next() {
    if (stepNumber === TOUR_STEPS.length) {
      await finish();
      return;
    }
    await move(stepNumber + 1);
  }

  async function back() {
    if (stepNumber > 1) await move(stepNumber - 1);
  }

  async function skip() {
    await finish();
  }

  return (
    <aside
      className="fixed bottom-5 right-5 z-[90] w-[min(390px,calc(100vw-2rem))] rounded-[22px] border border-[#54E1D0]/25 bg-[#0B1D33]/95 p-5 shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur-[28px]"
      aria-live="polite"
      aria-label={`GODFIN app tour, step ${stepNumber} of ${TOUR_STEPS.length}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[#54E1D0]/65 text-[0.62rem] uppercase tracking-[0.16em]">
            App tour · {stepNumber} of {TOUR_STEPS.length}
          </p>
          <h2 className="mt-1.5 text-white/90 text-lg font-medium">{step.title}</h2>
        </div>
        <button
          type="button"
          onClick={deactivateGuidedTour}
          aria-label="Close and resume the tour later"
          className="rounded-full p-1.5 text-white/35 hover:bg-white/[0.06] hover:text-white/70"
        >
          <X size={17} />
        </button>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-white/55">{step.body}</p>
      <div className="mt-3 rounded-xl border border-white/[0.08] bg-white/[0.04] p-3">
        <p className="text-[0.68rem] uppercase tracking-wide text-white/28">Try this</p>
        <p className="mt-1 text-xs leading-relaxed text-white/48">{step.lookFor}</p>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#17C3B2] to-[#A6E22E] transition-[width]"
          style={{ width: `${(stepNumber / TOUR_STEPS.length) * 100}%` }}
        />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={back}
          disabled={stepNumber === 1 || mutation.isPending}
          className="min-h-11 rounded-xl border border-white/[0.1] px-3 text-xs text-white/50 disabled:opacity-30"
        >
          <ChevronLeft size={15} className="inline" /> Back
        </button>
        <button
          type="button"
          onClick={skip}
          disabled={mutation.isPending}
          className="min-h-11 px-2 text-xs text-white/35 hover:text-white/60"
        >
          Skip tour
        </button>
        <button
          type="button"
          onClick={next}
          disabled={mutation.isPending}
          className="ml-auto min-h-11 rounded-xl border border-[#54E1D0]/25 bg-[#17C3B2]/10 px-4 text-xs text-[#B8FFF4]"
        >
          {stepNumber === TOUR_STEPS.length ? 'Finish' : 'Next'} <ChevronRight size={15} className="inline" />
        </button>
      </div>
      <p className="mt-2 text-[0.62rem] text-white/24">Close keeps your place. Skip marks the tour complete.</p>
    </aside>
  );
}
