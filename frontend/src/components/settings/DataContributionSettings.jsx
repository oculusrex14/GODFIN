import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Eye, HandCoins, ShieldCheck } from 'lucide-react';

import {
  fetchRewardPilotPreview,
  fetchRewardPilotStatus,
  submitRewardPilotBundle,
  updateRewardPilotConsent,
} from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { GlassButton } from '../GlassButton';

export default function DataContributionSettings() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { data: status } = useQuery({
    queryKey: ['rewardPilotStatus'],
    queryFn: fetchRewardPilotStatus,
  });
  const { data: preview, refetch: loadPreview, isFetching: previewing } = useQuery({
    queryKey: ['rewardPilotPreview'],
    queryFn: fetchRewardPilotPreview,
    enabled: false,
    retry: false,
  });
  const consentMutation = useMutation({
    mutationFn: updateRewardPilotConsent,
    onSuccess: data => {
      queryClient.setQueryData(['rewardPilotStatus'], data);
      queryClient.removeQueries({ queryKey: ['rewardPilotPreview'] });
      addToast(data.consented ? 'Pilot consent saved locally.' : 'Pilot consent withdrawn.', 'success');
    },
  });
  const submitMutation = useMutation({
    mutationFn: submitRewardPilotBundle,
    onSuccess: () => addToast('Aggregate bundle submitted for review.', 'success'),
  });

  if (!status) return null;

  return (
    <div className="space-y-4">
      <div className={`rounded-[16px] border p-4 ${
        status.enabled
          ? 'border-cyan-400/15 bg-cyan-400/[0.04]'
          : 'border-white/[0.08] bg-white/[0.025]'
      }`}>
        <div className="flex items-start gap-3">
          <HandCoins size={19} className="mt-0.5 text-cyan-200/55 shrink-0" />
          <div>
            <div className="text-white/75 text-sm">
              ₹50,000 privacy-safe research pilot
            </div>
            <p className="mt-1 text-white/35 text-xs leading-relaxed">
              {status.enabled
                ? 'Participation is separate, optional, and off by default.'
                : 'The pilot is currently closed. No finance data can leave this device.'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-2 text-[0.7rem]">
        <div className="rounded-[14px] bg-white/[0.03] p-3 text-white/35">
          <ShieldCheck size={14} className="mb-2 text-emerald-300/55" />
          Never includes names, account/card numbers, UPI IDs, emails, phones,
          addresses, exact dates, amounts, balances, or descriptions.
        </div>
        <div className="rounded-[14px] bg-white/[0.03] p-3 text-white/35">
          <CheckCircle2 size={14} className="mb-2 text-emerald-300/55" />
          ₹100 for the first accepted 90-day aggregate; capped template rewards
          may bring the participant maximum to ₹300.
        </div>
      </div>

      {status.enabled && (
        <>
          <label className="flex items-start gap-3 rounded-[14px] border border-white/[0.08] p-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 accent-cyan-400"
              checked={Boolean(status.consented)}
              disabled={consentMutation.isPending}
              onChange={event => consentMutation.mutate(event.target.checked)}
            />
            <span className="text-white/45 text-xs leading-relaxed">
              I separately consent to build a coarse aggregate preview on this
              computer under consent version {status.consent_version}. Nothing is
              submitted until I review the preview and press Submit.
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            <GlassButton
              variant="secondary"
              icon={<Eye size={14} />}
              disabled={!status.consented || previewing}
              onClick={() => loadPreview()}
            >
              {previewing ? 'Building preview…' : 'Preview redacted bundle'}
            </GlassButton>
            <GlassButton
              disabled={!preview?.eligible || submitMutation.isPending}
              onClick={() => submitMutation.mutate()}
            >
              {submitMutation.isPending ? 'Submitting…' : 'Submit reviewed bundle'}
            </GlassButton>
          </div>
        </>
      )}

      {preview && (
        <div className="rounded-[14px] border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
          <div className="text-emerald-200/70 text-xs">
            Local redaction checks passed · {preview.payload.transaction_count_band} transactions
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[0.68rem] text-white/35">
            <span>Window: {preview.payload.window_days} days</span>
            <span>Eligible: {preview.eligible ? 'yes' : 'not yet'}</span>
            <span>Dates/amounts: excluded</span>
            <span>Identifiers: excluded</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(preview.payload.category_share_bands_percent || {}).map(([category, share]) => (
              <span key={category} className="rounded-full bg-white/[0.05] px-2 py-1 text-[0.62rem] text-white/35">
                {category}: ~{share}%
              </span>
            ))}
          </div>
          <p className="mt-3 text-white/25 text-[0.65rem] break-all">
            Bundle digest: {preview.digest}
          </p>
        </div>
      )}
    </div>
  );
}
