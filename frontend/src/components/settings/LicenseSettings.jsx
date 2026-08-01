import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ExternalLink, RefreshCw, ShieldCheck } from 'lucide-react';

import {
  activateLicense,
  deactivateLicense,
  fetchLicenseStatus,
  verifyLicense,
} from '../../api/client';
import { GlassButton } from '../GlassButton';
import { useConfirm } from '../ConfirmDialog';
import { useToast } from '../../context/ToastContext';
import { openWebsite } from '../../config/website';

function formatDate(value) {
  if (!value) return 'Not verified';
  return new Date(value).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function LicenseSettings() {
  const [licenseKey, setLicenseKey] = useState('');
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { confirm, ConfirmDialog } = useConfirm();
  const { data: license, isLoading } = useQuery({
    queryKey: ['license'],
    queryFn: fetchLicenseStatus,
  });

  const refresh = (data) => {
    queryClient.setQueryData(['license'], data);
    queryClient.invalidateQueries({ queryKey: ['settingsHealth'] });
  };

  const activateMutation = useMutation({
    mutationFn: () => activateLicense(licenseKey),
    onSuccess: (data) => {
      setLicenseKey('');
      refresh(data);
      addToast(`GODFIN ${data.tier.toUpperCase()} activated.`, 'success');
    },
  });
  const verifyMutation = useMutation({
    mutationFn: verifyLicense,
    onSuccess: (data) => {
      refresh(data);
      addToast('License verified.', 'success');
    },
  });
  const deactivateMutation = useMutation({
    mutationFn: deactivateLicense,
    onSuccess: (data) => {
      refresh(data);
      addToast('This device is using GODFIN Core.', 'info');
    },
  });

  const handleDeactivate = async () => {
    const approved = await confirm({
      title: 'Remove license from this device?',
      message: 'Paid features will be locked until a license key is entered again. Your local finance data will not be deleted.',
      confirmLabel: 'Remove License',
      cancelLabel: 'Keep License',
      danger: true,
    });
    if (approved) deactivateMutation.mutate();
  };

  if (isLoading) {
    return <div className="text-white/30 text-[0.75rem]">Checking local license…</div>;
  }

  const active = license?.valid;
  return (
    <>
      <div className={`rounded-[16px] border p-4 ${
        active
          ? 'border-emerald-400/20 bg-emerald-400/[0.06]'
          : 'border-white/[0.1] bg-white/[0.03]'
      }`}>
        <div className="flex items-start gap-3">
          {active ? (
            <CheckCircle2 size={20} className="text-emerald-300 mt-0.5 shrink-0" />
          ) : (
            <ShieldCheck size={20} className="text-white/35 mt-0.5 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-white/80 text-[0.9rem]">
                GODFIN {(license?.tier || 'free').toUpperCase()}
              </strong>
              <span className={`rounded-full px-2 py-0.5 text-[0.62rem] uppercase tracking-wide ${
                active ? 'bg-emerald-400/10 text-emerald-300/80' : 'bg-white/[0.06] text-white/35'
              }`}>
                {license?.status?.replaceAll('_', ' ') || 'inactive'}
              </span>
            </div>
            <p className="mt-1.5 text-white/35 text-[0.72rem] leading-relaxed">
              {license?.message}
            </p>
            {license?.masked_key && (
              <div className="mt-2 font-mono text-[0.68rem] text-white/30 break-all">
                {license.masked_key}
              </div>
            )}
          </div>
        </div>
      </div>

      {active ? (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-[12px] bg-white/[0.03] p-3">
              <div className="text-white/25 text-[0.63rem] uppercase">Last verified</div>
              <div className="mt-1 text-white/55 text-[0.72rem]">{formatDate(license.verified_at)}</div>
            </div>
            <div className="rounded-[12px] bg-white/[0.03] p-3">
              <div className="text-white/25 text-[0.63rem] uppercase">Hosted AI</div>
              <div className="mt-1 text-white/55 text-[0.72rem]">
                No hosted credits are bundled or sold in this release.
              </div>
              <div className="mt-1 text-white/25 text-[0.65rem]">Local AI and your own supported provider key remain optional.</div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <GlassButton
              icon={<RefreshCw size={14} />}
              onClick={() => verifyMutation.mutate()}
              disabled={verifyMutation.isPending}
            >
              {verifyMutation.isPending ? 'Verifying…' : 'Verify now'}
            </GlassButton>
            <GlassButton variant="ghost" onClick={handleDeactivate} disabled={deactivateMutation.isPending}>
              Remove from device
            </GlassButton>
          </div>
        </div>
      ) : (
        <form
          className="mt-4"
          onSubmit={(event) => {
            event.preventDefault();
            activateMutation.mutate();
          }}
        >
          <label className="block text-white/45 text-[0.72rem] mb-2" htmlFor="license-key">
            Lifetime license key
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              id="license-key"
              autoComplete="off"
              spellCheck="false"
              value={licenseKey}
              onChange={(event) => setLicenseKey(event.target.value.toUpperCase())}
              placeholder="GODFIN-PRO-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"
              className="min-w-0 flex-1 rounded-[12px] border border-white/[0.12] bg-white/[0.05] px-3.5 py-2.5 font-mono text-[0.74rem] text-white/75 placeholder:text-white/18 focus:border-cyan-400/35 focus:outline-none"
            />
            <GlassButton type="submit" disabled={activateMutation.isPending || licenseKey.trim().length < 20}>
              {activateMutation.isPending ? 'Activating…' : 'Activate'}
            </GlassButton>
          </div>
        </form>
      )}

      <button
        type="button"
        className="mt-4 inline-flex items-center gap-1.5 text-cyan-300/65 hover:text-cyan-200 text-[0.7rem] transition-colors"
        onClick={() => openWebsite(active ? '/account' : '/pricing')}
      >
        {active ? 'Manage license' : 'View lifetime pricing'} <ExternalLink size={12} />
      </button>
      <ConfirmDialog />
    </>
  );
}
