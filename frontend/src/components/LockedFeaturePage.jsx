import { LockKeyhole } from 'lucide-react';

import { openWebsite } from '../config/website';
import { GlassButton } from './GlassButton';
import { GlassSection } from './GlassSection';

export default function LockedFeaturePage({ rule }) {
  const plan = rule?.required_tier === 'pro' ? 'Pro' : 'Max';
  return (
    <div className="mx-auto max-w-2xl py-10">
      <GlassSection>
        <div className="flex flex-col items-center px-4 py-10 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-200">
            <LockKeyhole size={26} aria-hidden="true" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold text-ink-primary">
            {rule?.label || 'This feature'} requires GODFIN {plan}
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-muted">
            {rule?.explanation || `Activate a GODFIN ${plan} lifetime license to use this feature.`}
          </p>
          <p className="mt-2 text-xs text-ink-muted">
            Your existing local data remains available and is never deleted by a plan change.
          </p>
          <GlassButton className="mt-6" onClick={() => openWebsite('/pricing')}>
            View lifetime plans
          </GlassButton>
        </div>
      </GlassSection>
    </div>
  );
}
