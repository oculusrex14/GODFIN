import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BrainCircuit,
  Download,
  Eye,
  RotateCcw,
  Trash2,
} from 'lucide-react';

import {
  downloadClassificationMemory,
  fetchClassificationMemory,
  resetClassificationMemory,
  undoClassificationCorrection,
  updatePersonalClassifier,
} from '../../api/client';
import { useToast } from '../../context/ToastContext';
import PinInput from '../PinInput';

export default function ClassificationMemorySettings() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [pin, setPin] = useState('');

  const { data } = useQuery({
    queryKey: ['classificationMemory'],
    queryFn: () => fetchClassificationMemory(100),
  });
  const undoMutation = useMutation({
    mutationFn: undoClassificationCorrection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classificationMemory'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      addToast('Learning correction undone.');
    },
  });
  const personalMutation = useMutation({
    mutationFn: updatePersonalClassifier,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['classificationMemory'] }),
  });
  const resetMutation = useMutation({
    mutationFn: resetClassificationMemory,
    onSuccess: result => {
      setResetOpen(false);
      setPin('');
      queryClient.invalidateQueries({ queryKey: ['classificationMemory'] });
      addToast(`Classification memory reset. Backup: ${result.backup_filename}`);
    },
  });

  const eligibility = data?.eligibility;
  const activeCorrections = (data?.corrections || []).filter(item => !item.undone);

  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-white/[0.09] bg-white/[0.035] p-3">
          <p className="text-white/25 text-[0.65rem] uppercase">Exact merchants</p>
          <p className="mt-1 text-white/75 text-xl font-light">{data?.merchants?.length || 0}</p>
        </div>
        <div className="rounded-xl border border-white/[0.09] bg-white/[0.035] p-3">
          <p className="text-white/25 text-[0.65rem] uppercase">Confirmed patterns</p>
          <p className="mt-1 text-white/75 text-xl font-light">{data?.patterns?.length || 0}</p>
        </div>
        <div className="rounded-xl border border-white/[0.09] bg-white/[0.035] p-3">
          <p className="text-white/25 text-[0.65rem] uppercase">Corrections</p>
          <p className="mt-1 text-white/75 text-xl font-light">{eligibility?.confirmed_corrections || 0}</p>
        </div>
      </div>

      <div className="rounded-xl border border-white/[0.09] bg-white/[0.035] p-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-white/65 text-sm flex items-center gap-2">
            <BrainCircuit size={15} className="text-cyan-200/60" />
            Optional personal classifier
          </p>
          <p className="mt-1 text-white/30 text-xs">
            {eligibility?.eligible
              ? 'Evidence threshold met. This local classifier can now be enabled.'
              : `${eligibility?.confirmed_corrections || 0}/${eligibility?.required_corrections || 200} corrections · ${eligibility?.category_count || 0}/${eligibility?.required_categories || 5} categories`}
          </p>
        </div>
        <button
          type="button"
          disabled={!eligibility?.eligible || personalMutation.isPending}
          onClick={() => personalMutation.mutate(!eligibility?.enabled)}
          className="min-h-11 px-4 rounded-xl border border-white/[0.1] bg-white/[0.05] text-white/55 disabled:opacity-35 text-sm"
        >
          {eligibility?.enabled ? 'Disable' : 'Enable when eligible'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setExpanded(value => !value)}
          className="min-h-11 px-4 rounded-xl border border-white/[0.1] text-white/50 text-sm flex items-center gap-2"
        >
          <Eye size={14} />
          {expanded ? 'Hide memory' : 'Inspect memory'}
        </button>
        <button
          type="button"
          onClick={downloadClassificationMemory}
          className="min-h-11 px-4 rounded-xl border border-white/[0.1] text-white/50 text-sm flex items-center gap-2"
        >
          <Download size={14} />
          Export CSV
        </button>
        <button
          type="button"
          onClick={() => setResetOpen(true)}
          className="min-h-11 px-4 rounded-xl border border-rose-300/[0.12] text-rose-100/55 text-sm flex items-center gap-2"
        >
          <Trash2 size={14} />
          Reset learned memory
        </button>
      </div>

      {expanded && (
        <div className="space-y-4">
          <div>
            <p className="text-white/30 text-xs uppercase tracking-wide mb-2">Generalized patterns</p>
            <div className="max-h-56 overflow-y-auto rounded-xl border border-white/[0.08] divide-y divide-white/[0.06]">
              {(data?.patterns || []).map(pattern => (
                <div key={pattern.id} className="p-3 flex items-center justify-between gap-4 text-xs">
                  <div>
                    <p className="text-white/60">{pattern.pattern}</p>
                    <p className="mt-1 text-white/25">{pattern.instrument} · {pattern.confirmations} confirmations</p>
                  </div>
                  <p className="text-cyan-100/55 text-right">{pattern.category}{pattern.subcategory ? ` / ${pattern.subcategory}` : ''}</p>
                </div>
              ))}
              {!data?.patterns?.length && <p className="p-3 text-white/25 text-xs">No generalized patterns yet.</p>}
            </div>
          </div>
          <div>
            <p className="text-white/30 text-xs uppercase tracking-wide mb-2">Recent explicit corrections</p>
            <div className="max-h-64 overflow-y-auto rounded-xl border border-white/[0.08] divide-y divide-white/[0.06]">
              {activeCorrections.map(correction => (
                <div key={correction.id} className="p-3 flex items-center justify-between gap-4 text-xs">
                  <div>
                    <p className="text-white/60">{correction.merchant}</p>
                    <p className="mt-1 text-white/25">{correction.old_category || 'Unclassified'} → {correction.new_category}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => undoMutation.mutate(correction.id)}
                    disabled={undoMutation.isPending}
                    className="min-h-11 px-3 rounded-xl text-white/45 hover:bg-white/[0.06] flex items-center gap-2"
                  >
                    <RotateCcw size={13} />
                    Undo
                  </button>
                </div>
              ))}
              {!activeCorrections.length && <p className="p-3 text-white/25 text-xs">No active corrections yet.</p>}
            </div>
          </div>
        </div>
      )}

      {resetOpen && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/65 p-4">
          <div role="dialog" aria-modal="true" aria-labelledby="reset-memory-title" className="w-full max-w-md rounded-2xl border border-white/[0.14] bg-[#102342] p-5">
            <h3 id="reset-memory-title" className="text-white/85 text-lg">Reset classification memory?</h3>
            <p className="mt-2 text-white/40 text-sm leading-relaxed">
              Exact merchant memory, generalized patterns, and correction history will be removed after a local backup. Existing transaction labels stay unchanged.
            </p>
            <div className="mt-4">
              <PinInput
                value={pin}
                onChange={setPin}
                minLength={4}
                maxLength={8}
                label="Enter your PIN to reset learned memory"
              />
            </div>
            {resetMutation.error && <p className="mt-2 text-rose-200/65 text-xs">{resetMutation.error.message}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setResetOpen(false)} className="min-h-11 px-4 rounded-xl text-white/45 text-sm">Cancel</button>
              <button
                type="button"
                disabled={pin.length < 4 || resetMutation.isPending}
                onClick={() => resetMutation.mutate(pin)}
                className="min-h-11 px-4 rounded-xl border border-rose-300/[0.15] bg-rose-400/[0.08] text-rose-100/65 disabled:opacity-35 text-sm"
              >
                Reset memory
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
