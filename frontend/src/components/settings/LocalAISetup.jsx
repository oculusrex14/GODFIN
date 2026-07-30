import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  Check,
  Cloud,
  Download,
  ExternalLink,
  HardDrive,
  Laptop,
  Loader2,
  ShieldCheck,
  Square,
  Zap,
} from 'lucide-react';

import {
  benchmarkLocalAI,
  cancelLocalAIDownload,
  chooseLocalAI,
  downloadLocalAIModel,
  fetchLocalAIDownload,
  fetchLocalAIProfile,
} from '../../api/client';
import { openExternalUrl } from '../../config/external';
import { useToast } from '../../context/ToastContext';

const CHOICES = [
  {
    id: 'local',
    title: 'Private AI on this computer',
    description: 'Use a validated local model. Your prompts stay on this device.',
    icon: Laptop,
  },
  {
    id: 'provider',
    title: 'Connect another AI provider',
    description: 'Bring your own provider key. GODFIN encrypts it locally.',
    icon: Cloud,
  },
  {
    id: 'none',
    title: 'Continue without AI',
    description: 'Imports, rules, calculations, budgets, and reports still work.',
    icon: ShieldCheck,
  },
];

function Detail({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl border border-white/[0.1] bg-white/[0.04] p-3">
      <div className="flex items-center gap-2 text-white/30 text-[0.67rem] uppercase tracking-wide">
        <Icon size={13} />
        {label}
      </div>
      <p className="mt-1.5 text-white/65 text-sm">{value}</p>
    </div>
  );
}

export default function LocalAISetup({ onChoiceComplete, compact = false }) {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approved, setApproved] = useState(false);
  const [benchmark, setBenchmark] = useState(null);

  const { data: profile, isLoading } = useQuery({
    queryKey: ['localAIProfile'],
    queryFn: fetchLocalAIProfile,
    staleTime: 30000,
  });
  const { data: downloadStatus } = useQuery({
    queryKey: ['localAIDownload'],
    queryFn: fetchLocalAIDownload,
    refetchInterval: query => (
      ['downloading', 'cancelling'].includes(query.state.data?.status) ? 1000 : false
    ),
  });

  const choiceMutation = useMutation({
    mutationFn: chooseLocalAI,
    onSuccess: data => {
      queryClient.invalidateQueries({ queryKey: ['localAIProfile'] });
      onChoiceComplete?.(data.choice);
    },
  });
  const downloadMutation = useMutation({
    mutationFn: downloadLocalAIModel,
    onSuccess: () => {
      setApprovalOpen(false);
      setApproved(false);
      queryClient.invalidateQueries({ queryKey: ['localAIDownload'] });
      addToast('Local model download started. You can leave this screen.', 'info');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: cancelLocalAIDownload,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['localAIDownload'] }),
  });
  const benchmarkMutation = useMutation({
    mutationFn: benchmarkLocalAI,
    onSuccess: result => setBenchmark(result),
  });

  const recommendation = profile?.recommendation;
  const model = recommendation?.model;
  const activeChoice = profile?.choice;
  const downloading = ['downloading', 'cancelling'].includes(downloadStatus?.status);

  function selectChoice(choice) {
    choiceMutation.mutate(choice);
  }

  if (isLoading) {
    return (
      <div className="min-h-24 grid place-items-center text-white/35 text-sm">
        <Loader2 className="animate-spin" size={18} aria-hidden="true" />
        <span className="sr-only">Checking this device</span>
      </div>
    );
  }

  return (
    <div className={compact ? 'space-y-4' : 'space-y-5'}>
      <div>
        <h3 className="text-white/80 text-lg">How should GODFIN handle AI?</h3>
        <p className="mt-1 text-white/35 text-sm">
          This is optional. Financial totals always come from verified local calculations, never an LLM.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-2.5" role="radiogroup" aria-label="AI setup choice">
        {CHOICES.map(choice => {
          const Icon = choice.icon;
          const selected = activeChoice === choice.id;
          return (
            <button
              key={choice.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => selectChoice(choice.id)}
              className={`min-h-[126px] text-left rounded-2xl border p-4 transition-colors ${
                selected
                  ? 'border-cyan-300/35 bg-cyan-400/[0.09]'
                  : 'border-white/[0.1] bg-white/[0.04] hover:bg-white/[0.07]'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <Icon size={19} className="text-cyan-200/70" />
                {selected && <Check size={16} className="text-emerald-300" />}
              </div>
              <div className="mt-3 text-white/75 text-sm">{choice.title}</div>
              <p className="mt-1 text-white/35 text-xs leading-relaxed">{choice.description}</p>
            </button>
          );
        })}
      </div>

      {activeChoice === 'local' && (
        <div className="rounded-2xl border border-white/[0.1] bg-white/[0.04] p-4 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-white/30 text-xs uppercase tracking-wide">Device check</p>
              <h4 className="mt-1 text-white/75">
                {model ? `${recommendation.label} is the comfortable default` : 'No local model recommended'}
              </h4>
              <p className="mt-1 max-w-2xl text-white/35 text-xs leading-relaxed">
                {recommendation?.reason}
              </p>
            </div>
            {!profile?.ollama?.installed && (
              <button
                type="button"
                onClick={() => openExternalUrl(profile.installer_url)}
                className="min-h-11 px-4 rounded-xl border border-cyan-300/20 bg-cyan-400/[0.08] text-cyan-100/75 text-sm flex items-center gap-2"
              >
                Open official Ollama installer
                <ExternalLink size={14} />
              </button>
            )}
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
            <Detail icon={Laptop} label="Memory" value={`${profile.total_ram_gb} GB total · ${profile.available_ram_gb} GB estimated free`} />
            <Detail icon={HardDrive} label="Disk" value={`${profile.disk_free_gb} GB free`} />
            <Detail icon={Zap} label="Acceleration" value={profile.acceleration.replaceAll('_', ' ')} />
            <Detail icon={Bot} label="Context limit" value={`${profile.context_tokens.toLocaleString()} tokens`} />
          </div>

          {model && (
            <div className="rounded-xl border border-white/[0.1] bg-black/10 p-3 text-xs text-white/40 space-y-1">
              <p><span className="text-white/65">Download:</span> about {recommendation.size_gb} GB</p>
              <p><span className="text-white/65">Estimated model memory:</span> {recommendation.memory_gb} GB</p>
              <p><span className="text-white/65">Expected speed:</span> {recommendation.expected_speed}</p>
              <p><span className="text-white/65">Privacy:</span> {profile.privacy}</p>
            </div>
          )}

          {downloading && (
            <div aria-live="polite">
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 rounded-full overflow-hidden bg-white/[0.08]">
                  <div
                    className="h-full bg-cyan-300/60 transition-[width]"
                    style={{ width: `${downloadStatus.progress || 0}%` }}
                  />
                </div>
                <span className="text-white/45 text-xs tabular-nums">{downloadStatus.progress || 0}%</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <p className="text-white/35 text-xs">{downloadStatus.message}</p>
                <button
                  type="button"
                  onClick={() => cancelMutation.mutate()}
                  className="min-h-11 px-3 rounded-xl text-rose-200/70 hover:bg-rose-400/[0.08] text-xs flex items-center gap-2"
                >
                  <Square size={12} />
                  Cancel
                </button>
              </div>
            </div>
          )}

          {downloadStatus?.status === 'failed' && (
            <div className="rounded-xl border border-rose-300/20 bg-rose-400/[0.06] p-3 text-rose-100/70 text-xs">
              {downloadStatus.message}
            </div>
          )}

          {downloadStatus?.status === 'complete' && (
            <div className="rounded-xl border border-emerald-300/20 bg-emerald-400/[0.06] p-3">
              <p className="text-emerald-100/75 text-sm">Model digest verified locally.</p>
              <p className="mt-1 text-white/25 text-[0.65rem] font-mono break-all">{downloadStatus.digest}</p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {model && profile?.ollama?.installed && !downloading && downloadStatus?.status !== 'complete' && (
              <button
                type="button"
                onClick={() => setApprovalOpen(true)}
                className="min-h-11 px-4 rounded-xl bg-cyan-400/10 border border-cyan-300/20 text-cyan-100/75 text-sm flex items-center gap-2"
              >
                <Download size={15} />
                Review download
              </button>
            )}
            {downloadStatus?.status === 'complete' && (
              <button
                type="button"
                onClick={() => benchmarkMutation.mutate(downloadStatus.model)}
                disabled={benchmarkMutation.isPending}
                className="min-h-11 px-4 rounded-xl bg-white/[0.07] border border-white/[0.12] text-white/65 text-sm flex items-center gap-2"
              >
                {benchmarkMutation.isPending ? <Loader2 className="animate-spin" size={15} /> : <Zap size={15} />}
                Run short finance benchmark
              </button>
            )}
          </div>

          {benchmark && (
            <p className="text-white/45 text-xs" aria-live="polite">
              Benchmark: {benchmark.tokens_per_second} tokens/second. The result is explanatory only; authoritative totals remain deterministic.
            </p>
          )}
        </div>
      )}

      {activeChoice === 'provider' && (
        <p className="rounded-xl border border-white/[0.1] bg-white/[0.04] p-3 text-white/45 text-sm">
          Use the provider configuration below to add an API key. You can change this choice at any time.
        </p>
      )}

      {activeChoice === 'none' && (
        <p className="rounded-xl border border-emerald-300/15 bg-emerald-400/[0.05] p-3 text-emerald-100/65 text-sm">
          AI is off. GODFIN’s deterministic imports, learned rules, calculations, and reports remain available.
        </p>
      )}

      {approvalOpen && model && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/65 p-4" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="local-model-approval-title"
            className="w-full max-w-lg rounded-2xl border border-white/[0.14] bg-[#102342] p-5 shadow-2xl"
          >
            <h3 id="local-model-approval-title" className="text-white/85 text-lg">Approve local model download</h3>
            <p className="mt-2 text-white/40 text-sm leading-relaxed">
              Ollama will download {recommendation.label} ({recommendation.size_gb} GB). This can use significant bandwidth and disk space.
            </p>
            <label className="mt-4 flex items-start gap-3 rounded-xl border border-white/[0.1] p-3 text-white/55 text-sm">
              <input
                type="checkbox"
                checked={approved}
                onChange={event => setApproved(event.target.checked)}
                className="mt-0.5"
              />
              I approve this download and understand I can cancel it.
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setApprovalOpen(false);
                  setApproved(false);
                }}
                className="min-h-11 px-4 rounded-xl text-white/45 hover:bg-white/[0.06] text-sm"
              >
                Not now
              </button>
              <button
                type="button"
                disabled={!approved || downloadMutation.isPending}
                onClick={() => downloadMutation.mutate(model)}
                className="min-h-11 px-4 rounded-xl bg-cyan-400/15 border border-cyan-300/20 text-cyan-100/80 disabled:opacity-40 text-sm"
              >
                Download model
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
