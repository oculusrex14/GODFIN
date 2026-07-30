import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Download,
  Eye,
  EyeOff,
  Gauge,
  Heart,
  Lightbulb,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

import {
  downloadBehaviorInsights,
  fetchBehaviorInsights,
  fetchLicenseStatus,
  fetchSponsorCard,
  resetBehaviorInsights,
  updateBehaviorConfig,
  updateBehaviorPreference,
} from '../api/client';
import CalculationInfo from '../components/CalculationInfo';
import { GlassButton } from '../components/GlassButton';
import { useToast } from '../context/ToastContext';

function displayValue(metric) {
  if (metric.value == null) return 'Not available';
  if (metric.unit === '%') return `${metric.value}%`;
  if (metric.unit === 'months') return `${metric.value} months`;
  return `${metric.value} / 100`;
}

export default function BehaviorInsights() {
  const [budget, setBudget] = useState('');
  const [notes, setNotes] = useState({});
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { data: license } = useQuery({ queryKey: ['license'], queryFn: fetchLicenseStatus });
  const entitled = license?.features?.includes('behavior_insights');
  const { data } = useQuery({
    queryKey: ['behaviorInsights'],
    queryFn: fetchBehaviorInsights,
    enabled: Boolean(entitled),
  });
  const { data: sponsor } = useQuery({
    queryKey: ['sponsorCard'],
    queryFn: fetchSponsorCard,
  });
  const updateCache = payload => queryClient.setQueryData(['behaviorInsights'], payload);
  const preferenceMutation = useMutation({
    mutationFn: ({ key, values }) => updateBehaviorPreference(key, values),
    onSuccess: updateCache,
  });
  const budgetMutation = useMutation({
    mutationFn: updateBehaviorConfig,
    onSuccess: payload => {
      updateCache(payload);
      addToast('Monthly comparison limit saved locally.', 'success');
    },
  });
  const resetMutation = useMutation({
    mutationFn: resetBehaviorInsights,
    onSuccess: payload => {
      updateCache(payload);
      setNotes({});
      setBudget('');
      addToast('Insight preferences reset.', 'success');
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-cyan-200/55" />
          <h1 className="text-white/90 text-[1.6rem] font-light">Your Money Habits</h1>
        </div>
        <p className="mt-1 text-white/30 text-sm">
          Gentle observations to help you notice patterns—not a judgment, diagnosis, or risk score
        </p>
      </div>

      {!entitled && license ? (
        <div className="rounded-[20px] border border-violet-400/15 bg-violet-400/[0.05] p-8 text-center">
          <Gauge className="mx-auto text-violet-200/45" size={34} />
          <h2 className="mt-3 text-white/75">Available with GODFIN Max</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-white/35">
            Plain-language observations and seven optional deeper measures show
            where every result came from. You can add context, hide, reset, or
            export each result.
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-[18px] border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck size={18} className="mt-0.5 shrink-0 text-emerald-200/60" />
              <p className="text-emerald-50/50 text-xs leading-relaxed">{data?.policy}</p>
            </div>
          </div>

          <section>
            <div className="mb-3 flex items-center gap-2">
              <Heart size={16} className="text-rose-200/55" />
              <div>
                <h2 className="text-white/80 text-lg font-light">Things worth reflecting on</h2>
                <p className="mt-0.5 text-white/28 text-xs">Read the observation, then decide whether it feels true for your life.</p>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {data?.reflections?.map((reflection) => (
                <article key={reflection.key} className="rounded-[18px] border border-[#54E1D0]/[0.13] bg-[#17C3B2]/[0.035] p-4">
                  <h3 className="text-white/78 text-sm font-medium">{reflection.title}</h3>
                  <p className="mt-2 text-white/48 text-sm leading-relaxed">{reflection.observation}</p>
                  <div className="mt-4 rounded-xl border border-white/[0.07] bg-black/10 p-3">
                    <p className="flex items-start gap-2 text-white/55 text-xs leading-relaxed">
                      <Lightbulb size={14} className="mt-0.5 shrink-0 text-[#A6E22E]/70" />
                      {reflection.question}
                    </p>
                    <p className="mt-2 pl-[22px] text-white/30 text-[0.7rem] leading-relaxed">{reflection.action}</p>
                  </div>
                  <p className="mt-3 text-white/22 text-[0.63rem]">{reflection.evidence} · {reflection.confidence} confidence</p>
                </article>
              ))}
            </div>
          </section>

          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="number"
              min="1"
              step="any"
              value={budget}
              onChange={event => setBudget(event.target.value)}
              placeholder={data?.monthly_budget ? `Current monthly limit: ${data.monthly_budget}` : 'Set monthly spending limit'}
              className="min-w-0 flex-1 rounded-[12px] border border-white/[0.12] bg-white/[0.05] px-3 py-2 text-sm text-white/70 placeholder:text-white/20 focus:outline-none"
            />
            <GlassButton
              icon={<Save size={14} />}
              disabled={!budget || budgetMutation.isPending}
              onClick={() => budgetMutation.mutate(Number(budget))}
            >
              Save limit
            </GlassButton>
            <GlassButton variant="secondary" icon={<Download size={14} />} onClick={downloadBehaviorInsights}>
              Export
            </GlassButton>
            <GlassButton variant="ghost" icon={<RotateCcw size={14} />} onClick={() => resetMutation.mutate()}>
              Reset
            </GlassButton>
          </div>

          <section>
            <div className="mb-3">
              <h2 className="text-white/70 text-lg font-light">The numbers behind your habits</h2>
              <p className="mt-1 text-white/25 text-xs">The simplest measures come first. Open the information bubble only when you want the full calculation.</p>
            </div>
          <div className="grid md:grid-cols-2 gap-4">
            {data?.metrics?.map(metric => (
              <article
                key={metric.key}
                className={`rounded-[18px] border p-4 transition-opacity ${
                  metric.hidden
                    ? 'border-white/[0.06] bg-white/[0.025] opacity-55'
                    : 'border-white/[0.1] bg-white/[0.055]'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-1">
                      <h2 className="text-white/70 text-sm">{metric.label}</h2>
                      <CalculationInfo
                        title={metric.label}
                        meaning={metric.meaning}
                        formula={metric.formula}
                        inputs={metric.inputs}
                        period={metric.period}
                        provenance={metric.provenance}
                        caveat={metric.caveat}
                      />
                    </div>
                    <p className="mt-1 text-white/25 text-[0.68rem]">
                      {metric.difficulty === 'easy' ? 'Easy to read' : metric.difficulty === 'intermediate' ? 'A little more detail' : 'Deeper measure'} · {metric.confidence} confidence
                    </p>
                  </div>
                  <button
                    aria-label={metric.hidden ? `Show ${metric.label}` : `Hide ${metric.label}`}
                    onClick={() => preferenceMutation.mutate({
                      key: metric.key,
                      values: { hidden: !metric.hidden },
                    })}
                    className="text-white/30 hover:text-white/60"
                  >
                    {metric.hidden ? <Eye size={15} /> : <EyeOff size={15} />}
                  </button>
                </div>
                <div className="mt-4 text-white/90 text-2xl font-light tabular-nums">
                  {displayValue(metric)}
                </div>
                <p className="mt-2 text-white/30 text-xs leading-relaxed">{metric.meaning}</p>
                <div className="mt-4 flex gap-2">
                  <input
                    value={notes[metric.key] ?? metric.correction_note ?? ''}
                    onChange={event => setNotes({ ...notes, [metric.key]: event.target.value })}
                    placeholder="Add a correction or context note"
                    className="min-w-0 flex-1 rounded-[10px] border border-white/[0.08] bg-black/10 px-2.5 py-2 text-[0.7rem] text-white/60 placeholder:text-white/18 focus:outline-none"
                  />
                  <button
                    onClick={() => preferenceMutation.mutate({
                      key: metric.key,
                      values: { correction_note: notes[metric.key] ?? metric.correction_note ?? '' },
                    })}
                    className="rounded-[10px] border border-white/[0.08] px-3 text-white/35 hover:text-white/65 text-xs"
                  >
                    Save
                  </button>
                </div>
              </article>
            ))}
          </div>
          </section>
        </>
      )}

      {sponsor?.visible && sponsor.sponsor && (
        <aside className="rounded-[16px] border border-white/[0.08] bg-white/[0.025] p-4">
          <div className="text-white/20 text-[0.58rem] uppercase tracking-widest">{sponsor.sponsor.label}</div>
          <div className="mt-1 text-white/45 text-sm">{sponsor.sponsor.title}</div>
          <p className="mt-1 text-white/25 text-xs">{sponsor.sponsor.body}</p>
          <p className="mt-2 text-white/18 text-[0.62rem]">
            Non-personalized · no financial-data targeting · no third-party scripts
          </p>
        </aside>
      )}
    </div>
  );
}
