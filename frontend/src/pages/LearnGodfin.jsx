import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  Bot,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  FileBarChart,
  KeyRound,
  Landmark,
  ListChecks,
  Lock,
  PiggyBank,
  ShieldCheck,
} from 'lucide-react';

import { fetchOnboardingStatus, updateOnboardingStatus } from '../api/client';
import { useLocation } from '../router';

const LESSONS = [
  {
    title: 'Your money stays yours',
    icon: Lock,
    summary: 'GODFIN is a local application. Ordinary financial data stays in SQLite on this computer.',
    points: [
      'Your PIN protects access to the local app.',
      'Cloud AI is optional; local AI and no-AI modes are available.',
      'Backups are local files that you control.',
    ],
    example: 'Practice data: Asha has ₹25,000 income and ₹8,000 spending. This example never enters your real database.',
  },
  {
    title: 'PIN, lock, and recovery',
    icon: KeyRound,
    summary: 'Use a memorable 4–6 digit PIN and lock the app whenever you step away.',
    points: [
      'Avoid easy sequences such as 1234 or a birth year.',
      'Repeated failures trigger a local cooldown to stop guessing attacks.',
      'Changing the PIN does not delete transactions.',
    ],
    example: 'Practice: use the Lock action in the sidebar; unlock again with your own PIN.',
  },
  {
    title: 'Accounts are containers',
    icon: Landmark,
    summary: 'An account represents one bank account, card, wallet, or cash source.',
    points: [
      'Accounts keep transactions from different sources separate.',
      'The account type helps transfer and cash-flow calculations.',
      'Deactivating an account preserves its history.',
    ],
    example: 'Practice data: “Asha Salary Account” and “Asha Credit Card” are synthetic accounts.',
  },
  {
    title: 'Import without fear',
    icon: Archive,
    summary: 'Upload a supported statement or connect Gmail bank alerts. GODFIN previews and deduplicates imports.',
    points: [
      'Review the selected account and date range before confirming.',
      'Duplicate checks prevent the same row from being added twice.',
      'Keep original statements outside the repository and back them up securely.',
    ],
    example: 'Practice row: 12 Jul · GREEN MART · ₹1,240 debit · pending category.',
  },
  {
    title: 'Categories explain purpose',
    icon: CreditCard,
    summary: 'Categories group spending by purpose; subcategories provide detail.',
    points: [
      'Use the category that best describes why the money moved.',
      'Transfers between your own accounts are not spending.',
      'The taxonomy is the same in imports, review, budgets, and reports.',
    ],
    example: 'Practice: GREEN MART → FOOD → Groceries. Monthly spending increases by ₹1,240.',
  },
  {
    title: 'Review teaches GODFIN',
    icon: ListChecks,
    summary: 'GODFIN learns only when you explicitly correct or confirm a transaction.',
    points: [
      'Exact merchant memory is the strongest learned rule.',
      'A confirmed pattern can help with similar future descriptions.',
      'You can inspect, undo, export, or reset learned memory.',
    ],
    example: 'Practice: changing “GREEN MART 8812” to Groceries teaches that confirmed pattern; finalized months never change.',
  },
  {
    title: 'Budgets are guardrails',
    icon: PiggyBank,
    summary: 'A budget compares planned limits with verified spending for the selected period.',
    points: [
      'Remaining budget = planned limit − spending so far.',
      'Savings rate = (income − expenses) ÷ income × 100.',
      'A ratio is context, not a judgment or financial recommendation.',
    ],
    example: 'Practice: ₹25,000 income − ₹8,000 expenses = ₹17,000 savings; savings rate = 68%.',
  },
  {
    title: 'Reports show evidence',
    icon: FileBarChart,
    summary: 'Reports summarize the transactions currently included in a selected date range.',
    points: [
      'Check the date range and account filters before interpreting a chart.',
      'Hover, focus, or tap an information bubble to see formulas and caveats.',
      'Exported totals come from deterministic calculations, not AI.',
    ],
    example: 'Practice: FOOD is 40% of ₹8,000 spending because ₹3,200 ÷ ₹8,000 × 100 = 40%.',
  },
  {
    title: 'Backups prevent regret',
    icon: ShieldCheck,
    summary: 'GODFIN keeps daily and weekly local backups, and you can create one before major changes.',
    points: [
      'The retention policy keeps the last 7 daily and last 4 weekly backups.',
      'Create a backup before imports, resets, or upgrades.',
      'Test recovery on a copy before you need it.',
    ],
    example: 'Practice: Settings → Backup & Export → Create Backup.',
  },
  {
    title: 'Licenses and optional AI',
    icon: Bot,
    summary: 'Lifetime plans unlock released app features. Hosted AI credits are always separate.',
    points: [
      'A paid license supports up to three active installations.',
      'Local AI and bring-your-own keys use no GODFIN credits.',
      'AI may explain verified calculations but never creates authoritative totals.',
    ],
    example: 'You can change AI mode later in Settings without affecting imports, rules, budgets, or reports.',
  },
];

export default function LearnGodfin() {
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
  const step = Math.min(LESSONS.length, Math.max(1, status?.tutorial_step || 1));
  const lesson = LESSONS[step - 1];
  const Icon = lesson.icon;

  async function move(nextStep) {
    await updateMutation.mutateAsync({ tutorial_step: nextStep });
  }

  async function next() {
    if (step === LESSONS.length) {
      await updateMutation.mutateAsync({
        tutorial_step: LESSONS.length,
        tutorial_completed: true,
      });
      navigate('/');
      return;
    }
    await move(step + 1);
  }

  async function back() {
    if (step > 1) await move(step - 1);
  }

  useEffect(() => {
    function onKeyDown(event) {
      if (event.target.closest('input, textarea, select, button, a')) return;
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        next();
      } else if (event.key === 'ArrowLeft' && step > 1) {
        event.preventDefault();
        back();
      } else if (event.key === 'Escape') {
        navigate('/');
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-cyan-300/55 text-xs uppercase tracking-[0.18em]">Learn GODFIN · Tutorial v{status?.tutorial_version || 1}</p>
          <h1 className="mt-2 text-white/90 text-2xl sm:text-3xl font-light">Finance basics, one calm step at a time</h1>
          <p className="mt-2 text-white/35 text-sm">All examples on this page are synthetic and are never saved as your financial data.</p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="min-h-11 px-4 rounded-xl text-white/45 hover:bg-white/[0.06] text-sm"
        >
          Leave and resume later
        </button>
      </header>

      <div className="h-2 rounded-full overflow-hidden bg-white/[0.07]" aria-label={`Lesson ${step} of ${LESSONS.length}`}>
        <div
          className="h-full bg-gradient-to-r from-cyan-300/65 to-emerald-300/65 transition-[width]"
          style={{ width: `${(step / LESSONS.length) * 100}%` }}
        />
      </div>

      <div className="grid lg:grid-cols-[240px_1fr] gap-5">
        <ol className="rounded-2xl border border-white/[0.09] bg-white/[0.035] p-2 space-y-1" aria-label="Tutorial lessons">
          {LESSONS.map((item, index) => {
            const number = index + 1;
            const active = number === step;
            const complete = number < step || status?.tutorial_completed;
            return (
              <li key={item.title}>
                <button
                  type="button"
                  onClick={() => move(number)}
                  aria-current={active ? 'step' : undefined}
                  className={`w-full min-h-11 rounded-xl px-3 flex items-center gap-3 text-left ${
                    active ? 'bg-white/[0.09] text-white/75' : 'text-white/35 hover:bg-white/[0.05]'
                  }`}
                >
                  <span className="w-5 text-center text-xs">{complete ? '✓' : number}</span>
                  <span className="text-xs">{item.title}</span>
                </button>
              </li>
            );
          })}
        </ol>

        <article className="rounded-2xl border border-white/[0.11] bg-white/[0.05] p-5 sm:p-7" aria-live="polite">
          <div className="w-12 h-12 grid place-items-center rounded-2xl bg-cyan-300/[0.09] border border-cyan-300/[0.15]">
            <Icon size={22} className="text-cyan-100/70" />
          </div>
          <p className="mt-5 text-white/25 text-xs uppercase tracking-wide">Lesson {step} of {LESSONS.length}</p>
          <h2 className="mt-1 text-white/85 text-2xl font-light">{lesson.title}</h2>
          <p className="mt-3 text-white/50 leading-relaxed">{lesson.summary}</p>
          <ul className="mt-5 space-y-3">
            {lesson.points.map(point => (
              <li key={point} className="flex gap-3 text-white/45 text-sm leading-relaxed">
                <span className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-cyan-300/55" />
                {point}
              </li>
            ))}
          </ul>
          <div className="mt-6 rounded-2xl border border-emerald-300/[0.13] bg-emerald-300/[0.045] p-4">
            <p className="text-emerald-100/45 text-[0.68rem] uppercase tracking-wide">Synthetic walkthrough</p>
            <p className="mt-2 text-white/55 text-sm leading-relaxed">{lesson.example}</p>
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={back}
              disabled={step === 1 || updateMutation.isPending}
              className="min-h-11 px-4 rounded-xl border border-white/[0.09] text-white/50 disabled:opacity-30 text-sm flex items-center gap-2"
            >
              <ChevronLeft size={15} />
              Back
            </button>
            <button
              type="button"
              onClick={next}
              disabled={updateMutation.isPending}
              className="min-h-11 px-4 rounded-xl border border-cyan-300/[0.18] bg-cyan-300/[0.08] text-cyan-100/75 text-sm flex items-center gap-2"
            >
              {step === LESSONS.length ? 'Finish tutorial' : 'Next lesson'}
              <ChevronRight size={15} />
            </button>
          </div>
          <p className="mt-4 text-white/20 text-[0.65rem]">
            Keyboard: Left/Right Arrow to move, Escape to leave. Buttons are touch-friendly and screen-reader labeled.
          </p>
        </article>
      </div>
    </div>
  );
}
