import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { AnimatePresence } from 'framer-motion';
import {
  Settings as SettingsIcon, Shield, Database, Download, Code, Mail, Cpu, Palette,
  Server, AlertTriangle, Plus, Trash2, X, Trash, Activity, CheckCircle2, KeyRound,
  Landmark, BookOpen, PlayCircle, RotateCcw, BrainCircuit,
} from 'lucide-react';
import {
  fetchSettings, fetchSettingsHealth, updateNetworkAccess, updateDeveloperMode, fetchDeveloperMode, triggerBackup, fetchBackups,
  downloadCSV, downloadSupportDiagnostics, fetchSystemStatus,
  createRule, deleteRule, resetData,
  fetchEmbeddingStatus, enableEmbeddings, disableEmbeddings,
  fetchOnboardingStatus, updateOnboardingStatus,
  prepareBackupRestore,
} from '../api/client';
import { GlassSection } from '../components/GlassSection';
import { GlassButton } from '../components/GlassButton';
import PinInput from '../components/PinInput';
import GmailSettings from '../components/settings/GmailSettings';
import LLMSettings from '../components/settings/LLMSettings';
import LocalAISetup from '../components/settings/LocalAISetup';
import ClassificationMemorySettings from '../components/settings/ClassificationMemorySettings';
import LicenseSettings from '../components/settings/LicenseSettings';
import AccountSettings from '../components/settings/AccountSettings';
import DataContributionSettings from '../components/settings/DataContributionSettings';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import { useConfirm } from '../components/ConfirmDialog';
import { useLocation } from '../router';
import { activateGuidedTour } from '../components/GuidedTour';
import DialogSurface from '../components/DialogSurface';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatBackupDate(value) {
  if (!value) return 'Date unavailable';
  return new Date(value).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function ToggleSwitch({ enabled, onChange, disabled, ariaLabel }) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={`
        relative w-12 h-7 rounded-full transition-all duration-300 backdrop-blur-md border overflow-hidden cursor-pointer hover:scale-105 active:scale-95
        ${enabled
          ? 'bg-emerald-500/20 border-emerald-400/30 shadow-[0_0_16px_rgba(52,211,153,0.2),inset_0_1px_0_rgba(255,255,255,0.15)]'
          : 'bg-white/[0.06] border-white/[0.12] shadow-[inset_0_2px_4px_rgba(0,0,0,0.2)]'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      {enabled && <div className="absolute inset-0 bg-gradient-to-r from-emerald-400/15 to-teal-400/15" />}
      <span className={`absolute top-0.5 h-6 w-6 rounded-full transition-all duration-300 shadow-lg ${
        enabled
          ? 'left-[calc(100%-1.625rem)] bg-gradient-to-br from-white to-slate-200 shadow-[0_2px_8px_rgba(0,0,0,0.3)]'
          : 'left-0.5 bg-gradient-to-br from-slate-300 to-slate-400 shadow-[0_2px_8px_rgba(0,0,0,0.3)]'
      }`}>
        <span className="absolute inset-0 rounded-full bg-gradient-to-br from-white/40 to-transparent" />
      </span>
    </button>
  );
}

function HealthItem({ label, health }) {
  const status = health?.status || 'unknown';
  const healthy = ['ok', 'connected', 'ready'].includes(status);
  const warning = ['never', 'not_configured', 'unknown'].includes(status);
  const tone = healthy
    ? 'text-emerald-300/80 bg-emerald-400/[0.08] border-emerald-400/[0.14]'
    : warning
      ? 'text-amber-300/80 bg-amber-400/[0.08] border-amber-400/[0.14]'
      : 'text-rose-300/80 bg-rose-400/[0.08] border-rose-400/[0.14]';
  return (
    <div className={`rounded-[14px] border p-3 ${tone}`}>
      <div className="flex items-center gap-2">
        {healthy ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
        <span className="text-[0.72rem] uppercase tracking-wide">{label}</span>
        <span className="ml-auto text-[0.62rem] uppercase opacity-60">{status.replaceAll('_', ' ')}</span>
      </div>
      <p className="mt-2 text-white/35 text-[0.68rem] leading-relaxed">
        {health?.message || 'Status unavailable.'}
      </p>
    </div>
  );
}

export default function Settings() {
  const { navigate } = useLocation();
  const { pinLength } = useAuth();
  const queryClient = useQueryClient();
  const { addToast: showToast } = useToast();
  const [csvMonth, setCsvMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [pendingSensitiveSetting, setPendingSensitiveSetting] = useState(null);
  const [sensitivePin, setSensitivePin] = useState('');
  const [pinError, setPinError] = useState('');
  const [showAddRule, setShowAddRule] = useState(false);
  const [ruleForm, setRuleForm] = useState({ rule_type: 'contains', pattern: '', category: '', subcategory: '', priority: 100 });
  const [showResetPin, setShowResetPin] = useState(false);
  const [resetPin, setResetPin] = useState('');
  const [resetPinError, setResetPinError] = useState('');
  const [restoreTarget, setRestoreTarget] = useState(null);
  const [restorePin, setRestorePin] = useState('');
  const [restoreError, setRestoreError] = useState('');
  const { confirm, ConfirmDialog: ConfirmDialogComponent } = useConfirm();

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });

  const { data: onboarding } = useQuery({
    queryKey: ['onboarding'],
    queryFn: fetchOnboardingStatus,
  });

  const { data: health } = useQuery({
    queryKey: ['settingsHealth'],
    queryFn: fetchSettingsHealth,
    refetchInterval: 30000,
  });

  const { data: devMode } = useQuery({
    queryKey: ['developerMode'],
    queryFn: fetchDeveloperMode,
  });

  const { data: backups } = useQuery({
    queryKey: ['backups'],
    queryFn: fetchBackups,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: fetchSystemStatus,
    refetchInterval: 30000,
  });

  const { data: embeddingStatus } = useQuery({
    queryKey: ['embeddingStatus'],
    queryFn: fetchEmbeddingStatus,
    refetchInterval: (query) => (
      ['queued', 'downloading', 'indexing'].includes(query.state.data?.status)
        ? 1000
        : false
    ),
  });

  const updateMutation = useMutation({
    mutationFn: ({ key, enabled, currentPin = null }) => {
      if (key === 'developer_mode') {
        return updateDeveloperMode(enabled, currentPin);
      }
      if (key === 'allow_network_access') {
        return updateNetworkAccess(enabled, currentPin);
      }
      throw new Error('Unsupported settings change');
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['developerMode'] });
      queryClient.invalidateQueries({ queryKey: ['settingsHealth'] });
      queryClient.invalidateQueries({ queryKey: ['embeddingStatus'] });
      if (data?.restart_required) {
        showToast('Quit and reopen GODFIN to apply the network-access change.', 'info');
      }
    },
  });

  const enableEmbeddingsMutation = useMutation({
    mutationFn: ({ enabled, currentPin }) => (
      enabled ? enableEmbeddings(currentPin) : disableEmbeddings(currentPin)
    ),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['embeddingStatus'] });
      setPendingSensitiveSetting(null);
      setSensitivePin('');
      setPinError('');
      showToast(
        data.enabled
          ? (data.started ? 'Similar-description matching setup started.' : 'Matching setup is already running.')
          : 'Similar-description matching is disabled.',
        'info',
      );
    },
    onError: error => setPinError(error?.message || 'This change could not be completed.'),
  });

  const learningMutation = useMutation({
    mutationFn: updateOnboardingStatus,
    onSuccess: data => queryClient.setQueryData(['onboarding'], data),
  });

  const backupMutation = useMutation({
    mutationFn: triggerBackup,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['backups'] });
      queryClient.invalidateQueries({ queryKey: ['settingsHealth'] });
      showToast(`Backup created: ${data.filename || 'success'}`);
    },
    onError: (err) => showToast(err?.message || 'Backup failed', 'error'),
  });

  const diagnosticsMutation = useMutation({
    mutationFn: downloadSupportDiagnostics,
    onSuccess: () => showToast('Support report downloaded.'),
    onError: (err) => showToast(err?.message || 'Support report could not be created.', 'error'),
  });

  const createRuleMutation = useMutation({
    mutationFn: createRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['developerMode'] });
      setShowAddRule(false);
      setRuleForm({ rule_type: 'contains', pattern: '', category: '', subcategory: '', priority: 100 });
      showToast('Rule created');
    },
    onError: (err) => showToast(err?.message || 'Failed to create rule', 'error'),
  });

  const deleteRuleMutation = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['developerMode'] });
      showToast('Rule deleted');
    },
  });

  const resetDataMutation = useMutation({
    mutationFn: ({ pin }) => resetData(pin),
    onSuccess: (data) => {
      setShowResetPin(false);
      setResetPinError('');
      queryClient.invalidateQueries();
      const msg = data.backup_created
        ? `Data reset. Backup saved: ${data.backup_filename}`
        : 'All data has been reset';
      showToast(msg, 'success');
    },
    onError: (err) => {
      setResetPinError(err?.message || 'Reset failed');
    },
  });

  const restoreMutation = useMutation({
    mutationFn: async ({ backup, pin }) => {
      if (typeof window.godfinDesktop?.restoreBackup !== 'function') {
        throw new Error('Backup restore is available in the GODFIN desktop app.');
      }
      const prepared = await prepareBackupRestore(backup.filename, pin);
      return window.godfinDesktop.restoreBackup(prepared.restore_token);
    },
    onSuccess: () => {
      setRestoreTarget(null);
      setRestorePin('');
      setRestoreError('');
      showToast('Backup restored. GODFIN is refreshing your local data.', 'success');
    },
    onError: (error) => {
      setRestoreError(error?.message || 'The backup could not be restored.');
    },
  });

  const devEnabled = settings?.developer_mode === 'true';

  const handleDevToggle = async (enable) => {
    if (enable && !devEnabled) {
      setPendingSensitiveSetting({ key: 'developer_mode', enabled: true });
      setSensitivePin('');
      setPinError('');
    } else {
      updateMutation.mutate({ key: 'developer_mode', enabled: false });
    }
  };

  const handlePinVerified = async () => {
    if (!pendingSensitiveSetting) return;
    if (sensitivePin.length < 4) {
      setPinError('Enter your current PIN.');
      return;
    }
    try {
      if (pendingSensitiveSetting.key === 'enable_embeddings') {
        await enableEmbeddingsMutation.mutateAsync({
          enabled: pendingSensitiveSetting.enabled,
          currentPin: sensitivePin,
        });
        return;
      }
      await updateMutation.mutateAsync({
        ...pendingSensitiveSetting,
        currentPin: sensitivePin,
      });
      setPendingSensitiveSetting(null);
      setSensitivePin('');
      setPinError('');
    } catch (error) {
      setPinError(error?.message || 'Invalid PIN');
    }
  };

  const handleNetworkToggle = (enable) => {
    if (enable) {
      setPendingSensitiveSetting({ key: 'allow_network_access', enabled: true });
      setSensitivePin('');
      setPinError('');
      return;
    }
    updateMutation.mutate({ key: 'allow_network_access', enabled: false });
  };

  const handleResetClick = async () => {
    const confirmed = await confirm({
      title: 'Reset All Data?',
      message: 'This will permanently delete transactions, audit sessions, merchant memories, goals, income sources, net-worth items, insight corrections, and prepared pilot bundles. A backup will be created first. Accounts and settings will be preserved. This action cannot be undone.',
      confirmLabel: 'Reset Everything',
      cancelLabel: 'Cancel',
      danger: true,
    });
    if (confirmed) {
      setShowResetPin(true);
      setResetPin('');
      setResetPinError('');
    }
  };

  const handleResetPinVerified = () => {
    if (resetPin.length < 4) {
      setResetPinError('Enter your current PIN.');
      return;
    }
    resetDataMutation.mutate({ pin: resetPin });
  };

  const handleRestoreClick = async (backup) => {
    const confirmed = await confirm({
      title: 'Restore this backup?',
      message: `Restore ${formatBackupDate(backup.created_at)}? GODFIN will first preserve the database you have now. Changes made after this backup will not appear after restore, but the safety copy can be recovered.`,
      confirmLabel: 'Continue to PIN',
      cancelLabel: 'Keep current data',
      danger: true,
    });
    if (!confirmed) return;
    setRestoreTarget(backup);
    setRestorePin('');
    setRestoreError('');
  };

  const handleRestorePinVerified = () => {
    if (restorePin.length < 4) {
      setRestoreError('Enter your current PIN.');
      return;
    }
    restoreMutation.mutate({ backup: restoreTarget, pin: restorePin });
  };

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <SettingsIcon className="h-5 w-5 text-white/30" />
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Settings</h1>
        </div>
      </motion.div>

      {health?.backup?.status === 'degraded' && (
        <div
          role="alert"
          aria-live="polite"
          className="rounded-[18px] border border-rose-400/25 bg-rose-400/[0.09] px-4 py-3 text-rose-100"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
            <div>
              <p className="text-sm font-medium">Automatic backup protection needs attention</p>
              <p className="mt-1 text-xs leading-relaxed text-white/55">{health.backup.message}</p>
              <p className="mt-2 text-[0.68rem] text-white/35">
                Last successful backup: {formatBackupDate(health.backup.last_success_at)}
                {health.backup.next_retry_at
                  ? ` · Next automatic retry: ${formatBackupDate(health.backup.next_retry_at)}`
                  : ''}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Trust & service health */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <GlassSection title="Trust & Service Health" icon={Activity} collapsible defaultExpanded={false} storageKey="godfin:settings:health-expanded">
          <div className="grid sm:grid-cols-2 gap-2.5">
            <HealthItem label="Encryption" health={health?.encryption} />
            <HealthItem label="Gmail" health={health?.gmail} />
            <HealthItem label="LLM" health={health?.llm} />
            <HealthItem label="Backups" health={health?.backup} />
            <HealthItem label="License" health={health?.license} />
          </div>
          <div className="mt-3 text-white/25 text-[0.68rem]">
            Last ingest: {health?.ingestion?.last_run || 'Never'}
          </div>
        </GlassSection>
      </motion.div>

      {/* Lifetime license */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.02 }}>
        <GlassSection title="Setup & Learning" icon={BookOpen} collapsible defaultExpanded={false} storageKey="godfin:settings:learning-expanded">
          <p className="text-white/35 text-sm leading-relaxed">
            Setup connects the parts you choose. Learn GODFIN explains money ideas. The separate app tour guides you through the real screens and can be closed or resumed at any time.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {!onboarding?.completed && (
              <GlassButton
                icon={<PlayCircle size={14} />}
                onClick={async () => {
                  await learningMutation.mutateAsync({ deferred: false });
                  navigate('/onboarding');
                }}
              >
                Resume setup
              </GlassButton>
            )}
            <GlassButton
              variant="secondary"
              icon={<BookOpen size={14} />}
              onClick={() => navigate('/learn')}
            >
              Learn GODFIN
            </GlassButton>
            <GlassButton
              variant="secondary"
              icon={<PlayCircle size={14} />}
              onClick={() => activateGuidedTour()}
            >
              {onboarding?.tutorial_completed ? 'Replay app tour' : 'Resume app tour'}
            </GlassButton>
            <GlassButton
              variant="secondary"
              icon={<RotateCcw size={14} />}
              onClick={async () => {
                await learningMutation.mutateAsync({ restart_tutorial: true });
                activateGuidedTour();
              }}
            >
              Restart app tour
            </GlassButton>
          </div>
          <p className="mt-3 text-white/25 text-xs">
            App tour v{onboarding?.tutorial_version || 1} · {onboarding?.tutorial_completed ? 'Completed' : `Step ${onboarding?.tutorial_step || 1} saved`}
          </p>
        </GlassSection>
      </motion.div>

      {/* Lifetime license */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }}>
        <GlassSection title="License & Plan" icon={KeyRound} collapsible defaultExpanded={false} storageKey="godfin:settings:license-expanded">
          <LicenseSettings />
        </GlassSection>
      </motion.div>

      {/* Local accounts and bank-parser routing */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.045 }}>
        <GlassSection title="Accounts & Import Routing" icon={Landmark} collapsible defaultExpanded={false} storageKey="godfin:settings:accounts-expanded">
          <AccountSettings />
        </GlassSection>
      </motion.div>

      {/* Gmail */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <GlassSection title="Gmail Integration" icon={Mail} collapsible defaultExpanded={false} storageKey="godfin:settings:gmail-expanded">
          <GmailSettings />
        </GlassSection>
      </motion.div>

      {/* AI Model */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <GlassSection title="AI Model Configuration" icon={Cpu} collapsible defaultExpanded={false} storageKey="godfin:settings:ai-expanded">
          <LocalAISetup compact />
          <div className="mt-5 pt-5 border-t border-white/[0.06]">
            <LLMSettings />
          </div>
          <div className="mt-4 pt-4 border-t border-white/[0.06]">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Web Search</div>
                <div className="text-white/25 text-[0.7rem]">Allow LLM to use web search for unfamiliar vendors</div>
              </div>
              <ToggleSwitch
                ariaLabel="Allow web search"
                enabled={settings?.llm_web_search === 'true'}
                onChange={(v) => updateMutation.mutate({ key: 'llm_web_search', value: v ? 'true' : 'false' })}
                disabled={updateMutation.isPending}
              />
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-white/[0.06]">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-white/70 text-[0.85rem]">Match similar transaction descriptions</div>
                <div className="text-white/25 text-[0.7rem]">
                  Helps GODFIN recognize differently written versions of the same kind of purchase. It is optional, works on this computer, and needs an initial download of about 100 MB.
                </div>
              </div>
              <ToggleSwitch
                ariaLabel="Match similar transaction descriptions"
                enabled={embeddingStatus?.enabled || false}
                onChange={async (enabled) => {
                  if (enabled) {
                    const approved = await confirm({
                      title: 'Download the matching helper?',
                      message: 'GODFIN will download about 100 MB to this computer. It helps compare similar transaction descriptions, but it is not required for imports, categories, budgets, or reports.',
                      confirmLabel: 'Download and enable',
                      cancelLabel: 'Not now',
                    });
                    if (approved) {
                      setSensitivePin('');
                      setPinError('');
                      setPendingSensitiveSetting({ key: 'enable_embeddings', enabled: true });
                    }
                  } else {
                    setSensitivePin('');
                    setPinError('');
                    setPendingSensitiveSetting({ key: 'enable_embeddings', enabled: false });
                  }
                }}
                disabled={enableEmbeddingsMutation.isPending}
              />
            </div>
            {embeddingStatus?.enabled && (
              <div className="mt-3">
                <div className="flex justify-between text-[0.67rem] text-white/30 mb-1.5">
                  <span>{embeddingStatus.message}</span>
                  <span>{embeddingStatus.progress || 0}%</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-400/70 to-emerald-400/70 transition-all duration-500"
                    style={{ width: `${embeddingStatus.progress || 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </GlassSection>
      </motion.div>

      {/* Backup & Export */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
        <GlassSection title="Backup & Export" icon={Database} collapsible defaultExpanded={false} storageKey="godfin:settings:backup-expanded">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Database Backup</div>
                <div className="text-white/25 text-[0.7rem]">Create a snapshot of your database</div>
              </div>
              <GlassButton icon={<Database size={14} />} onClick={() => backupMutation.mutate()} disabled={backupMutation.isPending}>
                {backupMutation.isPending ? 'Creating...' : 'Create Backup'}
              </GlassButton>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Export CSV</div>
                <div className="text-white/25 text-[0.7rem]">Download transactions as CSV</div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="month"
                  aria-label="Month to export as CSV"
                  value={csvMonth}
                  onChange={(e) => setCsvMonth(e.target.value)}
                  className="bg-white/[0.06] border border-white/[0.12] rounded-[10px] px-3 py-1.5 text-white/60 text-[0.8rem] focus:outline-none focus:border-cyan-400/30"
                />
                <GlassButton icon={<Download size={14} />} variant="secondary" onClick={() => downloadCSV(csvMonth)}>Download</GlassButton>
              </div>
            </div>
            {backups?.length > 0 && (
              <div className="pt-4 border-t border-white/[0.06]">
                <div className="text-white/30 text-[0.7rem] mb-2" style={{ fontWeight: 500 }}>Recent Backups</div>
                <div className="space-y-1.5">
                  {backups.slice(0, 5).map((b) => (
                    <div key={b.filename} className="flex flex-wrap items-center justify-between gap-2 text-[0.75rem] py-1">
                      <span className="text-white/40">{formatBackupDate(b.created_at)}</span>
                      <span className="flex flex-wrap items-center justify-end gap-2 text-white/20">
                        <span>{formatBytes(b.size_bytes)} · <span className="font-mono">{b.filename}</span></span>
                        {typeof window.godfinDesktop?.restoreBackup === 'function' && (
                          <button
                            type="button"
                            onClick={() => handleRestoreClick(b)}
                            disabled={!b.restore_ready || restoreMutation.isPending}
                            className="min-h-9 rounded-lg border border-amber-300/15 bg-amber-400/[0.06] px-2.5 text-[0.68rem] text-amber-100/65 transition-colors hover:bg-amber-400/[0.12] disabled:cursor-not-allowed disabled:opacity-35"
                            title={b.restore_ready ? 'Restore this verified backup' : 'This older backup has no verification record'}
                          >
                            Restore
                          </button>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </GlassSection>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}>
        <GlassSection title="Classification Learning" icon={BrainCircuit} collapsible defaultExpanded={false} storageKey="godfin:settings:classification-expanded">
          <p className="mb-4 text-white/35 text-sm leading-relaxed">
            GODFIN uses supervised learning from your explicit corrections—not reinforcement learning. Exact merchant memory is always the strongest learned match.
          </p>
          <ClassificationMemorySettings />
        </GlassSection>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.19 }}>
        <GlassSection title="Optional Data Contribution" icon={Shield} collapsible defaultExpanded={false} storageKey="godfin:settings:contribution-expanded">
          <DataContributionSettings />
        </GlassSection>
      </motion.div>

      {/* Developer Mode / Classification Diagnostics */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <GlassSection title={devEnabled ? 'Classification Diagnostics' : 'Developer Mode'} icon={Code} collapsible defaultExpanded={false} storageKey="godfin:settings:developer-expanded">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-white/70 text-[0.85rem]">Enable Developer Mode</div>
              <div className="text-white/25 text-[0.7rem]">Access classification health metrics and rules</div>
            </div>
            <ToggleSwitch ariaLabel="Developer mode" enabled={devEnabled} onChange={handleDevToggle} />
          </div>

          {/* Classification Health Metrics */}
          {devEnabled && devMode?.classification_health && (
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <div className="text-white/30 text-[0.7rem] mb-3" style={{ fontWeight: 500 }}>Classification Health</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
                {Object.entries(devMode.classification_health.source_counts || {}).map(([source, count]) => (
                  <div key={source} className="p-2.5 bg-white/[0.03] rounded-[10px]">
                    <div className="text-white/60 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>{count}</div>
                    <div className="text-white/25 text-[0.65rem] uppercase">{source}</div>
                    {devMode.classification_health.avg_confidence?.[source] != null && (
                      <div className="text-cyan-400/50 text-[0.6rem] mt-0.5">
                        {(devMode.classification_health.avg_confidence[source] * 100).toFixed(0)}% avg conf
                      </div>
                    )}
                  </div>
                ))}
                <div className="p-2.5 bg-amber-400/[0.04] rounded-[10px] border border-amber-400/[0.08]">
                  <div className="text-amber-400/70 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>
                    {devMode.classification_health.unclassified_count}
                  </div>
                  <div className="text-amber-400/40 text-[0.65rem] uppercase">Unclassified</div>
                </div>
                <div className="p-2.5 bg-white/[0.03] rounded-[10px]">
                  <div className="text-white/60 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>
                    {devMode.classification_health.merchant_memory_count}
                  </div>
                  <div className="text-white/25 text-[0.65rem] uppercase">Merchant Memory</div>
                </div>
                <div className="p-2.5 bg-white/[0.03] rounded-[10px]">
                  <div className="text-white/60 text-[1.1rem] tabular-nums" style={{ fontWeight: 300 }}>
                    {devMode.classification_health.active_rules_count}
                  </div>
                  <div className="text-white/25 text-[0.65rem] uppercase">Active Rules</div>
                </div>
              </div>
            </div>
          )}

          {devEnabled && (
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <div className="flex items-center justify-between mb-3">
                <div className="text-white/30 text-[0.7rem]" style={{ fontWeight: 500 }}>Classification Rules ({devMode?.rules?.length || 0})</div>
                <button onClick={() => setShowAddRule(!showAddRule)} className="text-cyan-400/60 text-[0.7rem] hover:text-cyan-300/80 flex items-center gap-1">
                  <Plus size={12} /> Add Rule
                </button>
              </div>

              {showAddRule && (
                <form
                  className="bg-white/[0.04] rounded-[12px] p-3 mb-3 space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    createRuleMutation.mutate({
                      rule_type: ruleForm.rule_type,
                      pattern: ruleForm.pattern,
                      category: ruleForm.category,
                      subcategory: ruleForm.subcategory || undefined,
                      priority: parseInt(ruleForm.priority) || 100,
                    });
                  }}
                >
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      aria-label="Classification rule match type"
                      value={ruleForm.rule_type}
                      onChange={(e) => setRuleForm(p => ({ ...p, rule_type: e.target.value }))}
                      className="bg-white/[0.06] border border-white/[0.1] rounded-lg px-2 py-1.5 text-[0.75rem] text-white/70 outline-none"
                    >
                      <option value="contains">Contains</option>
                      <option value="exact">Exact</option>
                      <option value="regex">Regex</option>
                    </select>
                    <input
                      aria-label="Classification rule pattern"
                      value={ruleForm.pattern}
                      onChange={(e) => setRuleForm(p => ({ ...p, pattern: e.target.value }))}
                      placeholder="Pattern"
                      required
                      className="bg-white/[0.06] border border-white/[0.1] rounded-lg px-2 py-1.5 text-[0.75rem] text-white/70 placeholder:text-white/20 outline-none"
                    />
                    <input
                      aria-label="Classification rule category"
                      value={ruleForm.category}
                      onChange={(e) => setRuleForm(p => ({ ...p, category: e.target.value }))}
                      placeholder="Category"
                      required
                      className="bg-white/[0.06] border border-white/[0.1] rounded-lg px-2 py-1.5 text-[0.75rem] text-white/70 placeholder:text-white/20 outline-none"
                    />
                    <input
                      aria-label="Classification rule subcategory"
                      value={ruleForm.subcategory}
                      onChange={(e) => setRuleForm(p => ({ ...p, subcategory: e.target.value }))}
                      placeholder="Subcategory (optional)"
                      className="bg-white/[0.06] border border-white/[0.1] rounded-lg px-2 py-1.5 text-[0.75rem] text-white/70 placeholder:text-white/20 outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      aria-label="Classification rule priority"
                      value={ruleForm.priority}
                      onChange={(e) => setRuleForm(p => ({ ...p, priority: e.target.value }))}
                      placeholder="Priority"
                      className="w-20 bg-white/[0.06] border border-white/[0.1] rounded-lg px-2 py-1.5 text-[0.75rem] text-white/70 placeholder:text-white/20 outline-none"
                    />
                    <span className="text-white/20 text-[0.65rem]">Priority (lower = higher)</span>
                    <div className="flex-1" />
                    <button type="button" onClick={() => setShowAddRule(false)} className="text-white/30 text-[0.7rem] hover:text-white/50 px-2 py-1">Cancel</button>
                    <button type="submit" disabled={createRuleMutation.isPending} className="bg-cyan-500/20 text-cyan-400/80 text-[0.7rem] px-3 py-1 rounded-lg hover:bg-cyan-500/30">
                      {createRuleMutation.isPending ? 'Creating...' : 'Create'}
                    </button>
                  </div>
                </form>
              )}

              <div className="max-h-48 overflow-y-auto space-y-1">
                {(devMode?.rules || []).map((rule) => (
                  <div key={rule.id} className="flex items-center gap-3 text-[0.7rem] bg-white/[0.03] rounded-[10px] px-3 py-2 group">
                    <span className="text-white/20 uppercase w-12 shrink-0">{rule.rule_type}</span>
                    <span className="text-amber-400/60 font-mono flex-1 truncate">{rule.pattern}</span>
                    <span className="text-emerald-400/60 shrink-0">{rule.category}</span>
                    {rule.subcategory && <span className="text-white/20 shrink-0">{rule.subcategory}</span>}
                    <span className="text-white/15 shrink-0">P{rule.priority}</span>
                    {!rule.is_system && (
                      <button
                        onClick={() => deleteRuleMutation.mutate(rule.id)}
                        className="text-white/0 group-hover:text-rose-400/50 hover:!text-rose-400/80 transition-colors shrink-0"
                        aria-label={`Delete classification rule ${rule.pattern}`}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </GlassSection>
      </motion.div>

      {/* App Settings */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
        <GlassSection
          title="App Settings"
          icon={SettingsIcon}
          collapsible
          defaultExpanded={false}
          storageKey="godfin:settings:app-settings-expanded"
        >
          <div className="space-y-3">
            {settings && Object.entries(settings)
              .filter(([key]) => !['pin_hash', 'developer_mode', 'backup_directory'].includes(key))
              .map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-[0.8rem]">
                  <span className="text-white/30 font-mono text-[0.7rem]">{key}</span>
                  <span className="text-white/50 text-[0.7rem] truncate max-w-[200px]">{value || '--'}</span>
                </div>
              ))}
          </div>
        </GlassSection>
      </motion.div>

      {/* System */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
        <GlassSection title="System" icon={Server} collapsible defaultExpanded={false} storageKey="godfin:settings:system-expanded">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Backend Status</div>
                <div className="text-white/25 text-[0.7rem]">{systemStatus?.status === 'ok' ? 'Running normally' : 'Status unknown'}</div>
              </div>
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${systemStatus?.status === 'ok' ? 'bg-emerald-400/80' : 'bg-amber-400/80'}`} />
                <span className="text-white/40 text-[0.7rem]">{systemStatus?.status === 'ok' ? 'Online' : 'Unknown'}</span>
              </div>
            </div>
            <div className="pt-4 border-t border-white/[0.06] flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Allow network access</div>
                <div className="text-white/25 text-[0.7rem]">
                  Off keeps GODFIN on this Mac. When enabled, other devices on your
                  trusted local network can reach GODFIN while it is running.
                </div>
              </div>
              <ToggleSwitch
                ariaLabel="Allow network access"
                enabled={['true', 'lan'].includes(settings?.allow_network_access)}
                onChange={handleNetworkToggle}
                disabled={updateMutation.isPending}
              />
            </div>
            <div className="pt-4 border-t border-white/[0.06] flex items-center justify-between gap-4">
              <div>
                <div className="text-white/70 text-[0.85rem]">Support report</div>
                <div className="text-white/25 text-[0.7rem]">
                  Download service health without transactions, credentials, account details, or local file paths.
                </div>
              </div>
              <GlassButton
                variant="secondary"
                icon={<Download size={14} />}
                onClick={() => diagnosticsMutation.mutate()}
                disabled={diagnosticsMutation.isPending}
              >
                {diagnosticsMutation.isPending ? 'Preparing…' : 'Download'}
              </GlassButton>
            </div>
            <div className="pt-4 border-t border-white/[0.06] rounded-xl text-white/30 text-[0.72rem] leading-relaxed">
              GODFIN does not run restart scripts from the settings screen. If a setting says a restart is required, quit and reopen the desktop app normally.
            </div>
          </div>
        </GlassSection>
      </motion.div>

      {/* Data Management */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
        <GlassSection title="Data Management" icon={Trash} collapsible defaultExpanded={false} storageKey="godfin:settings:data-expanded">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/70 text-[0.85rem]">Reset All Data</div>
                <div className="text-white/25 text-[0.7rem]">Delete dynamic finance data, including net-worth items and prepared pilot bundles. Accounts &amp; settings preserved.</div>
              </div>
              <GlassButton
                variant="secondary"
                icon={<Trash2 size={14} className="text-rose-400" />}
                onClick={handleResetClick}
                disabled={resetDataMutation.isPending}
              >
                Reset Data
              </GlassButton>
            </div>
          </div>
        </GlassSection>
      </motion.div>

      {/* Confirm Dialog */}
      <ConfirmDialogComponent />

      {/* PIN prompt for security-sensitive settings */}
      <AnimatePresence>
        {pendingSensitiveSetting && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => { setPendingSensitiveSetting(null); setSensitivePin(''); }} role="presentation">
            <DialogSurface
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              labelledBy="sensitive-setting-title"
              onClose={() => { setPendingSensitiveSetting(null); setSensitivePin(''); }}
              onClick={(e) => e.stopPropagation()}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-sm mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-4">
                <h3 id="sensitive-setting-title" className="text-white/90 text-[1rem]" style={{ fontWeight: 400 }}>
                  {pendingSensitiveSetting.key === 'developer_mode'
                    ? 'Enter PIN to enable Developer Mode'
                    : pendingSensitiveSetting.key === 'allow_network_access'
                      ? 'Enter PIN to allow network access'
                      : pendingSensitiveSetting.enabled
                        ? 'Enter PIN to enable matching'
                        : 'Enter PIN to disable matching'}
                </h3>
                <button
                  type="button"
                  aria-label="Close security confirmation"
                  onClick={() => { setPendingSensitiveSetting(null); setSensitivePin(''); }}
                  className="text-white/30 hover:text-white/60"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex justify-center">
                <PinInput
                  minLength={4}
                  maxLength={pinLength || 8}
                  displayLength={pinLength}
                  value={sensitivePin}
                  onChange={setSensitivePin}
                  autoSubmit={false}
                  disabled={updateMutation.isPending || enableEmbeddingsMutation.isPending}
                  label="Current PIN"
                />
              </div>
              {pendingSensitiveSetting.key === 'allow_network_access' && (
                <p className="mt-3 rounded-xl border border-amber-300/15 bg-amber-400/[0.06] p-3 text-center text-[0.7rem] leading-relaxed text-amber-100/60">
                  Only enable this on a trusted private network. Other devices on that
                  network may be able to reach your local GODFIN service after restart.
                </p>
              )}
              {pinError && <p className="text-rose-400/80 text-[0.75rem] text-center mt-3" role="alert">{pinError}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setPendingSensitiveSetting(null); setSensitivePin(''); }}
                  className="min-h-11 px-4 rounded-xl text-white/45 hover:bg-white/[0.06] text-sm"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handlePinVerified}
                  disabled={sensitivePin.length < 4 || updateMutation.isPending || enableEmbeddingsMutation.isPending}
                  className="min-h-11 px-4 rounded-xl bg-cyan-400/15 border border-cyan-300/20 text-cyan-100/80 disabled:opacity-40 text-sm"
                >
                  {updateMutation.isPending || enableEmbeddingsMutation.isPending ? 'Checking…' : 'Continue'}
                </button>
              </div>
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>

      {/* PIN Prompt Modal for Backup Restore */}
      <AnimatePresence>
        {restoreTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => { if (!restoreMutation.isPending) { setRestoreTarget(null); setRestorePin(''); } }} role="presentation">
            <DialogSurface
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              labelledBy="restore-backup-pin-title"
              onClose={() => { if (!restoreMutation.isPending) { setRestoreTarget(null); setRestorePin(''); } }}
              onClick={(event) => event.stopPropagation()}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-sm mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h3 id="restore-backup-pin-title" className="text-white/90 text-[1rem]" style={{ fontWeight: 400 }}>Enter PIN to Restore Backup</h3>
                  <p className="mt-1 text-[0.7rem] leading-relaxed text-white/35">GODFIN will close its local service, verify and restore this backup, then reopen it automatically.</p>
                </div>
                <button type="button" disabled={restoreMutation.isPending} onClick={() => { setRestoreTarget(null); setRestorePin(''); }} className="text-white/30 hover:text-white/60 disabled:opacity-40" aria-label="Close restore backup dialog"><X size={18} /></button>
              </div>
              <div className="flex justify-center">
                <PinInput
                  minLength={4}
                  maxLength={pinLength || 8}
                  displayLength={pinLength}
                  value={restorePin}
                  onChange={setRestorePin}
                  autoSubmit={false}
                  disabled={restoreMutation.isPending}
                  label="Current PIN"
                />
              </div>
              {restoreError && <p className="text-rose-400/80 text-[0.75rem] text-center mt-3" role="alert">{restoreError}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button type="button" disabled={restoreMutation.isPending} onClick={() => { setRestoreTarget(null); setRestorePin(''); }} className="min-h-11 px-4 rounded-xl text-white/45 hover:bg-white/[0.06] disabled:opacity-40 text-sm">Cancel</button>
                <button type="button" onClick={handleRestorePinVerified} disabled={restorePin.length < 4 || restoreMutation.isPending} className="min-h-11 px-4 rounded-xl bg-amber-400/15 border border-amber-300/20 text-amber-100/80 disabled:opacity-40 text-sm">
                  {restoreMutation.isPending ? 'Restoring…' : 'Restore backup'}
                </button>
              </div>
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>

      {/* PIN Prompt Modal for Data Reset */}
      <AnimatePresence>
        {showResetPin && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => { setShowResetPin(false); setResetPin(''); }} role="presentation">
            <DialogSurface
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              labelledBy="reset-data-pin-title"
              onClose={() => { setShowResetPin(false); setResetPin(''); }}
              onClick={(e) => e.stopPropagation()}
              className="relative overflow-hidden rounded-[24px] bg-[#0d2040]/95 backdrop-blur-[32px] border border-white/[0.15] p-6 w-full max-w-sm mx-4 shadow-[0_16px_64px_rgba(0,0,0,0.3)]"
            >
              <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              <div className="flex items-center justify-between mb-4">
                <h3 id="reset-data-pin-title" className="text-white/90 text-[1rem]" style={{ fontWeight: 400 }}>Enter PIN to Reset Data</h3>
                <button onClick={() => { setShowResetPin(false); setResetPin(''); }} className="text-white/30 hover:text-white/60" aria-label="Close reset data dialog"><X size={18} /></button>
              </div>
              <div className="flex justify-center">
                <PinInput
                  minLength={4}
                  maxLength={pinLength || 8}
                  displayLength={pinLength}
                  value={resetPin}
                  onChange={setResetPin}
                  autoSubmit={false}
                  disabled={resetDataMutation.isPending}
                  label="Current PIN"
                />
              </div>
              {resetPinError && <p className="text-rose-400/80 text-[0.75rem] text-center mt-3" role="alert">{resetPinError}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setShowResetPin(false); setResetPin(''); }}
                  className="min-h-11 px-4 rounded-xl text-white/45 hover:bg-white/[0.06] text-sm"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleResetPinVerified}
                  disabled={resetPin.length < 4 || resetDataMutation.isPending}
                  className="min-h-11 px-4 rounded-xl bg-rose-400/15 border border-rose-300/20 text-rose-100/80 disabled:opacity-40 text-sm"
                >
                  {resetDataMutation.isPending ? 'Checking…' : 'Reset data'}
                </button>
              </div>
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
