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
  if (!metric.available || metric.value == null) return 'Not ready yet';
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
          <Sparkles size={18} className="text-cyan-200" />
          <h1 className="text-ink-primary text-[1.6rem] font-light">Your Money Habits</h1>
        </div>
        <p className="mt-1 text-ink-muted text-sm">
          Gentle observations to help you notice patterns—not a judgment, diagnosis, or risk score
        </p>
      </div>

      {!entitled && license ? (
        <div className="rounded-[20px] border border-violet-400/15 bg-violet-400/[0.05] p-8 text-center">
          <Gauge className="mx-auto text-violet-200" size={34} />
          <h2 className="mt-3 text-ink-secondary">Available with GODFIN Max</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-ink-muted">
            Plain-language observations and seven optional deeper measures show
            where every result came from. You can add context, hide, reset, or
            export each result.
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-[18px] border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck size={18} className="mt-0.5 shrink-0 text-emerald-200" />
              <p className="text-emerald-50 text-xs leading-relaxed">{data?.policy}</p>
            </div>
          </div>

          {data?.coverage && (
            <div className="rounded-[18px] border border-white/[0.09] bg-white/[0.035] p-4">
              <p className="text-ink-secondary text-sm">
                Based on the previous six finished calendar months
              </p>
              <p className="mt-1 text-ink-muted text-xs leading-relaxed">
                {data.period} · {data.coverage.observed_months} of 6 months contain usable activity · {data.coverage.included_transactions} included transactions
              </p>
              <p className="mt-2 text-ink-muted text-[0.68rem] leading-relaxed">
                {data.coverage.note}
              </p>
            </div>
          )}

          <section>
            <div className="mb-3 flex items-center gap-2">
              <Heart size={16} className="text-rose-200" />
              <div>
                <h2 className="text-ink-primary text-lg font-light">Things worth reflecting on</h2>
                <p className="mt-0.5 text-ink-muted text-xs">Read the observation, then decide whether it feels true for your life.</p>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {data?.reflections?.map((reflection) => (
                <article key={reflection.key} className="rounded-[18px] border border-[#54E1D0]/[0.13] bg-[#17C3B2]/[0.035] p-4">
                  <h3 className="text-ink-primary text-sm font-medium">{reflection.title}</h3>
                  <p className={`mt-2 text-sm leading-relaxed ${reflection.available ? 'text-ink-muted' : 'text-amber-100'}`}>
                    {reflection.observation}
                  </p>
                  {reflection.available && (
                    <div className="mt-4 rounded-xl border border-white/[0.07] bg-black/10 p-3">
                      <p className="flex items-start gap-2 text-ink-secondary text-xs leading-relaxed">
                        <Lightbulb size={14} className="mt-0.5 shrink-0 text-[#A6E22E]/70" />
                        {reflection.question}
                      </p>
                      <p className="mt-2 pl-[22px] text-ink-muted text-[0.7rem] leading-relaxed">{reflection.action}</p>
                    </div>
                  )}
                  <p className="mt-3 text-ink-muted text-[0.63rem]">
                    {reflection.evidence}{reflection.available ? ` · ${reflection.confidence} confidence` : ' · More history needed'}
                  </p>
                </article>
              ))}
            </div>
          </section>

          <div className="flex flex-col sm:flex-row gap-2">
            <input
              aria-label="Monthly spending limit"
              type="number"
              min="1"
              step="any"
              value={budget}
              onInput={event => setBudget(event.currentTarget.value)}
              placeholder={data?.monthly_budget ? `Current monthly limit: ${data.monthly_budget}` : 'Set monthly spending limit'}
              className="min-w-0 flex-1 rounded-[12px] border border-white/[0.12] bg-white/[0.05] px-3 py-2 text-sm text-ink-secondary placeholder:text-ink-muted focus:outline-none"
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
              <h2 className="text-ink-secondary text-lg font-light">The numbers behind your habits</h2>
              <p className="mt-1 text-ink-muted text-xs">The simplest measures come first. Open the information bubble only when you want the full calculation.</p>
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
                      <h2 className="text-ink-secondary text-sm">{metric.label}</h2>
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
                    <p className="mt-1 text-ink-muted text-[0.68rem]">
                      {metric.available
                        ? `${metric.difficulty === 'easy' ? 'Easy to read' : metric.difficulty === 'intermediate' ? 'A little more detail' : 'Deeper measure'} · ${metric.confidence} confidence`
                        : 'Waiting for enough reliable information'}
                    </p>
                  </div>
                  <button
                    aria-label={metric.hidden ? `Show ${metric.label}` : `Hide ${metric.label}`}
                    onClick={() => preferenceMutation.mutate({
                      key: metric.key,
                      values: { hidden: !metric.hidden },
                    })}
                    className="text-ink-muted hover:text-ink-secondary"
                  >
                    {metric.hidden ? <Eye size={15} /> : <EyeOff size={15} />}
                  </button>
                </div>
                <div className="mt-4 text-ink-primary text-2xl font-light tabular-nums">
                  {displayValue(metric)}
                </div>
                <p className="mt-2 text-ink-muted text-xs leading-relaxed">{metric.meaning}</p>
                {!metric.available && metric.unavailable_reason && (
                  <p className="mt-3 rounded-xl border border-amber-300/[0.12] bg-amber-300/[0.04] px-3 py-2 text-amber-100 text-[0.7rem] leading-relaxed">
                    {metric.unavailable_reason}
                  </p>
                )}
                <div className="mt-4 flex gap-2">
                  <input
                    aria-label={`Correction or context note for ${metric.label}`}
                    value={notes[metric.key] ?? metric.correction_note ?? ''}
                    onChange={event => setNotes({ ...notes, [metric.key]: event.target.value })}
                    placeholder="Add a correction or context note"
                    className="min-w-0 flex-1 rounded-[10px] border border-white/[0.08] bg-black/10 px-2.5 py-2 text-[0.7rem] text-ink-secondary placeholder:text-ink-muted focus:outline-none"
                  />
                  <button
                    onClick={() => preferenceMutation.mutate({
                      key: metric.key,
                      values: { correction_note: notes[metric.key] ?? metric.correction_note ?? '' },
                    })}
                    className="rounded-[10px] border border-white/[0.08] px-3 text-ink-muted hover:text-ink-secondary text-xs"
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
          <div className="text-ink-muted text-[0.58rem] uppercase tracking-widest">{sponsor.sponsor.label}</div>
          <div className="mt-1 text-ink-muted text-sm">{sponsor.sponsor.title}</div>
          <p className="mt-1 text-ink-muted text-xs">{sponsor.sponsor.body}</p>
          <p className="mt-2 text-ink-muted text-[0.62rem]">
            Non-personalized · no financial-data targeting · no third-party scripts
          </p>
        </aside>
      )}
    </div>
  );
}
