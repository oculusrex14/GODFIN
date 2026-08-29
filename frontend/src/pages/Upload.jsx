import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import {
  Upload as UploadIcon, FileText, CheckCircle, AlertTriangle,
  Plus, Trash2, ArrowRight, ArrowLeft, Loader2, XCircle,
  DollarSign, FileCheck, AlertCircle, ChevronDown, Check,
} from 'lucide-react';
import {
  createIncomeSource, fetchReviewQueue, resolveReviewItem, fetchCategories,
  fetchAccounts, fetchLicenseStatus,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import MappedSpreadsheetImport from '../components/MappedSpreadsheetImport';
import { openWebsite } from '../config/website';
import { useUploadQueue } from '../context/UploadQueueContext';

function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB limit

const SUPPORTED_EXTENSIONS = ['.pdf', '.xls', '.xlsx'];

function validateFile(file) {
  if (!file) return { valid: false, error: 'No file selected' };
  const name = file.name.toLowerCase();
  if (!SUPPORTED_EXTENSIONS.some(ext => name.endsWith(ext))) {
    return { valid: false, error: 'Supported formats: PDF, XLS, XLSX' };
  }
  if (file.size > MAX_FILE_SIZE) {
    return { valid: false, error: 'File size must be less than 10MB' };
  }
  return { valid: true };
}

function isExcelFile(file) {
  if (!file) return false;
  const name = file.name.toLowerCase();
  return name.endsWith('.xls') || name.endsWith('.xlsx');
}

function automaticFileId(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function automaticQueueEntry(file) {
  return {
    id: automaticFileId(file),
    file,
    step: 1,
    status: 'waiting',
    password: '',
    accountId: '',
    reconcileData: null,
    importResult: null,
    error: '',
    progress: 0,
    progressLabel: '',
  };
}

function automaticAccountLabel(account) {
  return account.nickname
    || `${account.bank} ${account.account_type.replaceAll('_', ' ')} ••••${account.last_4_digits}`;
}

function StatementProgress({ value = 0, label, detail }) {
  return (
    <div
      className="mt-3 rounded-[14px] border border-cyan-400/[0.12] bg-cyan-400/[0.04] p-3"
      role="progressbar"
      aria-label={label}
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow={Math.round(value)}
    >
      <div className="mb-2 flex items-center justify-between gap-3 text-[0.7rem]">
        <span className="text-cyan-100">{label}</span>
        <span className="tabular-nums text-ink-muted">{Math.round(value)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500/70 to-teal-300/80"
          animate={{ width: `${Math.max(2, value)}%` }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
        />
      </div>
      {detail && <p className="mt-2 text-[0.64rem] leading-relaxed text-ink-muted">{detail}</p>}
    </div>
  );
}

export default function UploadPage() {
  const [importMode, setImportMode] = useState('automatic');
  const {
    automaticQueue,
    setAutomaticQueue,
    activeAutomaticId,
    setActiveAutomaticId,
    reviewAllFirst,
    setReviewAllFirst,
    isProcessing,
    updateAutomatic,
    reviewAutomatic,
    importAutomatic,
  } = useUploadQueue();
  const [fileError, setFileError] = useState('');

  const activeAutomatic = automaticQueue.find(item => item.id === activeAutomaticId)
    || automaticQueue[0]
    || null;
  const step = activeAutomatic?.step || 1;
  const file = activeAutomatic?.file || null;
  const password = activeAutomatic?.password || '';
  const reconcileData = activeAutomatic?.reconcileData || null;
  const importResult = activeAutomatic?.importResult || null;
  const activeStatus = activeAutomatic?.status || 'waiting';

  // Review panel state
  const [expandedReviewId, setExpandedReviewId] = useState(null);
  const [reviewCategory, setReviewCategory] = useState({});
  const [reviewSubcategory, setReviewSubcategory] = useState({});

  const queryClient = useQueryClient();
  const { data: license } = useQuery({
    queryKey: ['license'],
    queryFn: fetchLicenseStatus,
    staleTime: 5 * 60 * 1000,
  });
  const batchAvailable = license?.features?.includes('batch_statement_import') === true;
  const mappedImportAvailable = license?.features?.includes('generic_mapped_import') === true;

  const { data: importAccounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
  });

  // Review panel queries
  const { data: uploadReviewData } = useQuery({
    queryKey: ['uploadReviewQueue'],
    queryFn: () => fetchReviewQueue({ page_size: 50 }),
    refetchInterval: 10000,
  });

  const { data: categories } = useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
  });

  const reviewResolveMutation = useMutation({
    mutationFn: ({ transactionId, category, subcategory }) =>
      resolveReviewItem(transactionId, category, subcategory),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['uploadReviewQueue'] });
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['categoryBreakdown'] });
      setReviewCategory(prev => { const next = { ...prev }; delete next[variables.transactionId]; return next; });
      setReviewSubcategory(prev => { const next = { ...prev }; delete next[variables.transactionId]; return next; });
      setExpandedReviewId(null);
    },
  });

  function handleDrop(e) {
    e.preventDefault();
    addAutomaticFiles(Array.from(e.dataTransfer.files));
  }

  function addAutomaticFiles(files) {
    const errors = [];
    const acceptedFiles = batchAvailable ? files : files.slice(0, 1);
    if (!batchAvailable && files.length > 1) {
      errors.push('Core imports one statement at a time. Pro and Max add the guided batch queue.');
    }
    const known = new Set(automaticQueue.map(item => item.id));
    const additions = [];
    for (const candidate of acceptedFiles) {
      const validation = validateFile(candidate);
      if (!validation.valid) {
        errors.push(`${candidate.name}: ${validation.error}`);
        continue;
      }
      const entry = automaticQueueEntry(candidate);
      if (!known.has(entry.id)) {
        known.add(entry.id);
        additions.push(entry);
      }
    }
    setAutomaticQueue(current => [...current, ...additions]);
    if (
      additions.length
      && (!activeAutomaticId || activeAutomatic?.status === 'complete')
    ) {
      setActiveAutomaticId(additions[0].id);
    }
    setFileError(errors.join(' '));
  }

  function resetResults(id = activeAutomatic?.id) {
    if (!id) return;
    updateAutomatic(id, {
      step: 1,
      status: 'waiting',
      reconcileData: null,
      importResult: null,
      error: '',
      progress: 0,
      progressLabel: '',
    });
  }

  function removeAutomatic(id = activeAutomatic?.id) {
    if (!id || isProcessing) return;
    const index = automaticQueue.findIndex(item => item.id === id);
    const remaining = automaticQueue.filter(item => item.id !== id);
    setAutomaticQueue(remaining);
    if (activeAutomaticId === id) {
      setActiveAutomaticId(remaining[Math.min(index, remaining.length - 1)]?.id || null);
    }
  }

  function handleNextFile() {
    const next = automaticQueue.find(item => item.status !== 'complete');
    if (next) {
      setActiveAutomaticId(next.id);
      return;
    }
    setActiveAutomaticId(null);
  }

  const allAutomaticReviewed = automaticQueue.length > 0 && automaticQueue.every(
    item => ['reviewed', 'complete'].includes(item.status),
  );
  const automaticComplete = automaticQueue.filter(item => item.status === 'complete').length;
  const automaticFailed = automaticQueue.filter(item => item.status === 'failed').length;
  const automaticTotals = automaticQueue.reduce((totals, item) => ({
    imported: totals.imported + (item.importResult?.new_imported || 0),
    duplicates: totals.duplicates + (item.importResult?.matched || 0),
    review: totals.review + (item.importResult?.review_queue || 0),
  }), { imported: 0, duplicates: 0, review: 0 });

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-ink-primary text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Upload Statement</h1>
        <p className="text-ink-muted text-[0.8rem]">Import transactions from a recognized statement or map a spreadsheet safely</p>
      </motion.div>

      <div className="mb-5 inline-flex rounded-[14px] border border-white/[0.1] bg-white/[0.04] p-1" role="tablist" aria-label="Statement import method">
        <button
          type="button"
          role="tab"
          aria-selected={importMode === 'automatic'}
          onClick={() => setImportMode('automatic')}
          className={`rounded-[10px] px-4 py-2 text-[0.73rem] transition-colors ${
            importMode === 'automatic'
              ? 'bg-cyan-400/[0.12] text-cyan-200'
              : 'text-ink-muted hover:text-ink-secondary'
          }`}
        >
          Recognized HDFC statement
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={importMode === 'guided'}
          onClick={() => (
            mappedImportAvailable
              ? setImportMode('guided')
              : openWebsite('/pricing')
          )}
          className={`rounded-[10px] px-4 py-2 text-[0.73rem] transition-colors ${
            importMode === 'guided'
              ? 'bg-cyan-400/[0.12] text-cyan-200'
              : 'text-ink-muted hover:text-ink-secondary'
          }`}
        >
          Guided CSV / XLSX{mappedImportAvailable ? '' : ' · Pro'}
        </button>
      </div>

      {importMode === 'guided' && mappedImportAvailable ? (
        <MappedSpreadsheetImport />
      ) : (
        <>
      <section className="mb-5 rounded-[16px] border border-white/[0.1] bg-white/[0.04] p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[0.73rem] text-ink-secondary">Statement queue</p>
            <p className="mt-0.5 text-[0.65rem] text-ink-muted">
              {batchAvailable
                ? 'Files are reviewed one at a time, so a large batch cannot overwhelm your computer.'
                : 'Core imports one statement at a time. Pro and Max add a reviewed batch queue.'}
            </p>
          </div>
          <label className="cursor-pointer rounded-[10px] border border-cyan-400/20 bg-cyan-400/[0.06] px-3 py-2 text-[0.7rem] text-cyan-200 hover:bg-cyan-400/[0.1]">
            <Plus size={12} className="mr-1 inline" /> Add statements
            <input
              type="file"
              accept=".pdf,.xls,.xlsx"
              multiple={batchAvailable}
              className="hidden"
              onChange={(event) => {
                addAutomaticFiles(Array.from(event.target.files || []));
                event.target.value = '';
              }}
            />
          </label>
        </div>
        {automaticQueue.length > 0 && (
          <>
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
              {automaticQueue.map(item => (
                <div
                  key={item.id}
                  className={`flex min-w-[180px] max-w-[260px] items-center rounded-[10px] border ${
                    activeAutomatic?.id === item.id
                      ? 'border-cyan-400/25 bg-cyan-400/[0.07]'
                      : 'border-white/[0.07] bg-white/[0.025]'
                  }`}
                >
                  <button
                    type="button"
                    disabled={isProcessing}
                    onClick={() => setActiveAutomaticId(item.id)}
                    className="min-w-0 flex-1 px-3 py-2 text-left disabled:cursor-not-allowed"
                  >
                    <span className="block truncate text-[0.68rem] text-ink-secondary">{item.file.name}</span>
                    <span className={`block text-[0.58rem] capitalize ${
                      item.status === 'complete'
                        ? 'text-emerald-200'
                        : item.status === 'failed'
                          ? 'text-rose-200'
                          : 'text-ink-muted'
                    }`}>{item.status}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${item.file.name}`}
                    disabled={isProcessing}
                    onClick={() => removeAutomatic(item.id)}
                    className="mr-2 rounded p-1 text-ink-muted hover:text-rose-200 disabled:cursor-not-allowed"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-2">
              <label className="flex items-center gap-2 text-[0.66rem] text-ink-muted">
                <input
                  type="checkbox"
                  checked={reviewAllFirst}
                  onChange={event => setReviewAllFirst(event.target.checked)}
                  className="accent-cyan-400"
                />
                Review every file before importing any of them
              </label>
              <span className="text-[0.63rem] text-ink-muted">
                {automaticComplete} complete · {automaticFailed} failed · {automaticQueue.length} total
              </span>
            </div>
            {(automaticComplete > 0 || automaticFailed > 0) && (
              <p className="mt-2 text-[0.63rem] text-ink-muted">
                Batch summary: {automaticTotals.imported} imported · {automaticTotals.duplicates} duplicates skipped · {automaticTotals.review} need category review · {automaticFailed} failed
              </p>
            )}
          </>
        )}
        {fileError && <p className="mt-2 text-[0.68rem] text-rose-200">{fileError}</p>}
      </section>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-5">
        {[
          { num: 1, label: 'Upload' },
          { num: 2, label: 'Review' },
          { num: 3, label: 'Complete' },
        ].map((s, i) => (
          <div key={s.num} className="flex items-center gap-2">
            {i > 0 && <div className={`w-8 h-[1px] ${step >= s.num ? 'bg-cyan-400/40' : 'bg-white/[0.08]'}`} />}
            <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[0.7rem] border transition-all ${
              step === s.num
                ? 'bg-cyan-500/20 text-cyan-200 border-cyan-400/30'
                : step > s.num
                  ? 'bg-emerald-500/10 text-emerald-200 border-emerald-400/20'
                  : 'bg-white/[0.04] text-ink-muted border-white/[0.08]'
            }`}>
              {step > s.num ? <CheckCircle size={11} /> : <span>{s.num}</span>}
              {s.label}
            </div>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        {/* Left column: Upload / Review / Results */}
        <div>
          <AnimatePresence mode="wait">
            {/* Step 1: File Upload */}
            {step === 1 && (
              <motion.div
                key="step1"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-6"
              >
                <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
                <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Bank Statement</h2>

                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  className={`border-2 border-dashed rounded-[16px] p-8 text-center transition-all duration-300 ${
                    file ? 'border-emerald-400/20 bg-emerald-400/[0.03]' : 'border-white/[0.1] hover:border-white/[0.2]'
                  }`}
                >
                  {fileError && (
                    <p className="mb-2 text-rose-200 text-sm">{fileError}</p>
                  )}
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileText className="h-7 w-7 text-emerald-200" />
                      <div className="text-left">
                        <p className="text-ink-primary text-[0.85rem]">{file.name}</p>
                        <p className="text-ink-muted text-[0.7rem]">{(file.size / 1024).toFixed(1)} KB</p>
                      </div>
                      <button onClick={() => removeAutomatic()} className="ml-2 text-ink-muted hover:text-rose-200" aria-label={`Remove selected file ${file.name}`}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ) : (
                    <label className="cursor-pointer">
                      <UploadIcon className="h-9 w-9 text-ink-muted mx-auto mb-3" />
                      <p className="text-ink-muted text-[0.85rem] mb-1">Drop one or more PDF or Excel files here, or click to browse</p>
                      <p className="text-ink-muted text-[0.7rem]">HDFC Savings or Credit Card statement (PDF, XLS, XLSX)</p>
                      <input
                        type="file"
                        accept=".pdf,.xls,.xlsx"
                        multiple={batchAvailable}
                        onChange={(e) => {
                          addAutomaticFiles(Array.from(e.target.files || []));
                          e.target.value = '';
                        }}
                        className="hidden"
                      />
                    </label>
                  )}
                </div>

                {fileError && (
                  <p className="mt-2 text-rose-200 text-sm">{fileError}</p>
                )}

                {!isExcelFile(file) && (
                  <div className="mt-4">
                    <GlassInput
                      type="password"
                      placeholder="PDF password (if protected)"
                      value={password}
                      onChange={(e) => updateAutomatic(activeAutomatic.id, { password: e.target.value })}
                    />
                  </div>
                )}

                {file && (
                  <label className="mt-4 grid gap-1.5">
                    <span className="text-[0.68rem] text-ink-muted">Import into account</span>
                    <select
                      value={activeAutomatic?.accountId || ''}
                      onChange={event => updateAutomatic(activeAutomatic.id, { accountId: event.target.value })}
                      className="rounded-[10px] border border-white/[0.12] bg-[#15294a] px-3 py-2 text-[0.75rem] text-ink-secondary focus:border-cyan-400/40 focus:outline-none"
                    >
                      <option value="">Detect from the statement</option>
                      {importAccounts.filter(account => account.is_active !== false).map(account => (
                        <option key={account.id} value={account.id}>{automaticAccountLabel(account)}</option>
                      ))}
                    </select>
                    <span className="text-[0.62rem] leading-relaxed text-ink-muted">
                      Choose an account when you have more than one matching account. GODFIN still verifies the statement before import.
                    </span>
                  </label>
                )}

                <div className="mt-4">
                  <GlassButton
                    onClick={() => reviewAutomatic(activeAutomatic)}
                    disabled={!file || isProcessing}
                    className="w-full justify-center"
                  >
                    {activeStatus === 'parsing' ? (
                      <><Loader2 size={15} className="animate-spin" /> Parsing...</>
                    ) : (
                      <><FileCheck size={15} /> Upload & Reconcile</>
                    )}
                  </GlassButton>
                </div>

                {activeAutomatic?.status === 'parsing' && (
                  <StatementProgress
                    value={activeAutomatic.progress}
                    label={activeAutomatic.progressLabel}
                    detail="GODFIN is reading the statement on this computer. You can leave this page; the rest of the app remains available."
                  />
                )}

                {activeAutomatic?.status === 'failed' && activeAutomatic?.error && (
                  <div className="mt-3 p-3 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                    <p className="text-rose-200 text-[0.8rem]">{activeAutomatic.error}</p>
                  </div>
                )}
              </motion.div>
            )}

            {/* Step 2: Reconciliation Review */}
            {step === 2 && (
              <motion.div
                key="step2"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-6"
              >
                <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />

                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 500 }}>Reconciliation Review</h2>
                  <button onClick={() => resetResults()} className="text-ink-muted hover:text-ink-secondary text-[0.7rem] flex items-center gap-1 transition-colors">
                    <ArrowLeft size={12} /> Start Over
                  </button>
                </div>

                {activeStatus === 'reconciling' ? (
                  <div className="py-5">
                    <div className="flex items-center gap-3">
                      <Loader2 size={24} className="animate-spin text-cyan-200" />
                      <p className="text-ink-muted text-[0.85rem]">Checking which transactions are new or already present…</p>
                    </div>
                    <StatementProgress
                      value={activeAutomatic?.progress}
                      label={activeAutomatic?.progressLabel || 'Comparing transactions'}
                      detail="No changes are being made yet. GODFIN will show the review before saving anything."
                    />
                  </div>
                ) : activeAutomatic?.status === 'failed' ? (
                  <div className="p-4 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                    <p className="text-rose-200 text-[0.8rem] flex items-center gap-2">
                      <XCircle size={14} /> {activeAutomatic?.error}
                    </p>
                    <button onClick={() => resetResults()} className="mt-2 text-ink-muted text-[0.75rem] hover:text-ink-secondary">
                      Try again
                    </button>
                  </div>
                ) : reconcileData ? (
                  <>
                    <div className="mb-4 rounded-[12px] border border-emerald-400/15 bg-emerald-400/[0.05] p-3">
                      <p className="flex items-center gap-2 text-[0.75rem] text-emerald-200">
                        <CheckCircle size={14} /> Financial controls passed
                      </p>
                      <p className="mt-1 text-[0.68rem] leading-relaxed text-ink-muted">
                        GODFIN recognized {reconcileData.parser_profile?.replaceAll('_', ' ')} and verified the statement&apos;s explicit amount columns{reconcileData.reconciliation_method === 'explicit_columns_and_running_balance' ? ' against its running balances' : ''}. Import starts only after you confirm below.
                      </p>
                      <p className="mt-1 text-[0.62rem] text-ink-muted">
                        Parser {reconcileData.parser_profile?.replaceAll('_', ' ')} · reviewed file {reconcileData.parse_fingerprint?.slice(0, 12)}…
                      </p>
                    </div>
                    {/* Summary counters */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                      {[
                        { label: 'Total Parsed', val: reconcileData.total_parsed, color: 'text-ink-primary' },
                        { label: 'Matched', val: reconcileData.matched_count, color: 'text-emerald-200' },
                        { label: 'Possible Dupes', val: reconcileData.possible_count, color: 'text-amber-200' },
                        { label: 'New', val: reconcileData.new_count, color: 'text-cyan-200' },
                      ].map((s) => (
                        <div key={s.label} className="text-center p-2 bg-white/[0.03] rounded-[12px]">
                          <p className={`text-[1.3rem] tabular-nums ${s.color}`} style={{ fontWeight: 300 }}>{s.val}</p>
                          <p className="text-ink-muted text-[0.65rem]">{s.label}</p>
                        </div>
                      ))}
                    </div>

                    {/* New transactions list */}
                    {reconcileData.new_transactions?.length > 0 && (
                      <div className="mb-4">
                        <h3 className="text-cyan-200 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          New Transactions ({reconcileData.new_count})
                        </h3>
                        <div className="space-y-1 max-h-[200px] overflow-y-auto pr-1">
                          {reconcileData.new_transactions.map((t, i) => (
                            <div key={i} className="flex justify-between items-center text-[0.75rem] py-1.5 px-2 bg-white/[0.02] rounded-[8px]">
                              <div className="flex-1 min-w-0">
                                <span className="text-ink-muted truncate block">{t.description}</span>
                                <span className="text-ink-muted text-[0.65rem]">{t.date}</span>
                              </div>
                              <span className={`ml-2 tabular-nums ${t.type === 'credit' ? 'text-emerald-200' : 'text-ink-secondary'}`}>
                                {t.type === 'credit' ? '+' : '-'}{formatINR(t.amount)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Potential duplicates */}
                    {reconcileData.potential_duplicates?.length > 0 && (
                      <div className="mb-4">
                        <h3 className="text-amber-200 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          <AlertTriangle className="h-3 w-3 inline mr-1" />
                          Possible Duplicates ({reconcileData.possible_count})
                        </h3>
                        <div className="space-y-1 max-h-[150px] overflow-y-auto pr-1">
                          {reconcileData.potential_duplicates.map((d, i) => (
                            <div key={i} className="text-[0.7rem] py-1.5 px-2 bg-amber-400/[0.03] rounded-[8px] border border-amber-400/[0.08]">
                              <div className="text-ink-muted">{d.parsed.description} — {formatINR(d.parsed.amount)}</div>
                              <div className="text-ink-muted">Matches: {d.existing.merchant} — {formatINR(d.existing.amount)} ({d.existing.date})</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Income detected */}
                    {reconcileData.income_detected?.length > 0 && (
                      <div className="mb-4 p-3 bg-emerald-400/[0.04] rounded-[12px] border border-emerald-400/[0.1]">
                        <h3 className="text-emerald-200 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          <DollarSign className="h-3 w-3 inline mr-1" />
                          Income Detected ({reconcileData.income_count})
                        </h3>
                        <div className="space-y-1">
                          {reconcileData.income_detected.map((item, i) => (
                            <div key={i} className="flex justify-between text-[0.75rem]">
                              <span className="text-ink-muted">{item.description}</span>
                              <span className="text-emerald-200 tabular-nums">{formatINR(item.amount)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Import button / progress */}
                    {activeStatus === 'importing' ? (
                      <StatementProgress
                        value={activeAutomatic?.progress}
                        label={activeAutomatic?.progressLabel || 'Saving the reviewed statement'}
                        detail={`GODFIN is updating ${reconcileData.new_count} new transaction${reconcileData.new_count === 1 ? '' : 's'}, the review queue, matching, and the verified account balance. Other tabs remain usable.`}
                      />
                    ) : (
                      <GlassButton
                        onClick={() => importAutomatic(activeAutomatic)}
                        disabled={reviewAllFirst && !allAutomaticReviewed}
                        className="w-full justify-center mt-2"
                      >
                        {reconcileData.new_count === 0 ? (
                          <><CheckCircle size={15} /> Verify Statement Balance</>
                        ) : reviewAllFirst && !allAutomaticReviewed ? (
                          <>Review the remaining queued files first</>
                        ) : (
                          <><ArrowRight size={15} /> Import {reconcileData.new_count} New Transactions</>
                        )}
                      </GlassButton>
                    )}

                    {activeAutomatic?.error && (
                      <div className="mt-3 p-3 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                        <p className="text-rose-200 text-[0.8rem]">{activeAutomatic.error}</p>
                      </div>
                    )}
                  </>
                ) : null}
              </motion.div>
            )}

            {/* Step 3: Import Results */}
            {step === 3 && importResult && (
              <motion.div
                key="step3"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-6"
              >
                <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-emerald-400/30 to-transparent" />

                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="h-5 w-5 text-emerald-200" />
                  <h2 className="text-emerald-200 text-[0.85rem]" style={{ fontWeight: 500 }}>Import Complete</h2>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {[
                    { label: 'Total Parsed', val: importResult.total_parsed, color: 'text-ink-primary' },
                    { label: 'Matched (Skipped)', val: importResult.matched, color: 'text-emerald-200' },
                    { label: 'New Imported', val: importResult.new_imported, color: 'text-cyan-200' },
                    { label: 'Auto-Classified', val: importResult.classified, color: 'text-blue-200' },
                  ].map((s) => (
                    <div key={s.label} className="text-center p-2 bg-white/[0.03] rounded-[12px]">
                      <p className={`text-[1.3rem] tabular-nums ${s.color}`} style={{ fontWeight: 300 }}>{s.val}</p>
                      <p className="text-ink-muted text-[0.65rem]">{s.label}</p>
                    </div>
                  ))}
                </div>

                {importResult.review_queue > 0 && (
                  <div className="mb-3 p-2.5 bg-amber-400/[0.05] rounded-[10px] border border-amber-400/[0.1]">
                    <p className="text-amber-200 text-[0.75rem]">
                      <AlertTriangle className="h-3 w-3 inline mr-1" />
                      {importResult.review_queue} transaction(s) need manual review
                    </p>
                  </div>
                )}

                {importResult.income_items?.length > 0 && (
                  <div className="mb-3 p-3 bg-emerald-400/[0.04] rounded-[12px] border border-emerald-400/[0.1]">
                    <h3 className="text-emerald-200 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                      <DollarSign className="h-3 w-3 inline mr-1" />
                      Income Detected ({importResult.income_detected})
                    </h3>
                    <div className="space-y-2">
                      {importResult.income_items.map((item, i) => (
                        <div key={i} className="flex items-center justify-between text-[0.75rem] p-2 bg-white/[0.02] rounded-[8px]">
                          <div className="flex-1 min-w-0">
                            <span className="text-ink-muted block truncate">{item.description}</span>
                            <span className="text-emerald-200 tabular-nums">{formatINR(item.amount)}</span>
                          </div>
                          <button
                            onClick={() => {
                              createIncomeSource({
                                source_name: item.description,
                                expected_amount: item.amount,
                                frequency: 'monthly',
                              }).then(() => {
                                queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
                              });
                            }}
                            className="ml-2 px-2.5 py-1 text-[0.65rem] bg-emerald-500/20 text-emerald-200 rounded-lg hover:bg-emerald-500/30 transition-colors whitespace-nowrap"
                          >
                            <Plus size={10} className="inline mr-0.5" /> Add as Income
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {automaticQueue.some(item => item.status !== 'complete') ? (
                  <GlassButton onClick={handleNextFile} className="w-full justify-center mt-2">
                    <UploadIcon size={15} /> Continue With Next Statement
                  </GlassButton>
                ) : (
                  <label className="mt-2 flex w-full cursor-pointer items-center justify-center gap-2 rounded-[12px] border border-cyan-400/20 bg-cyan-400/[0.08] px-4 py-2.5 text-[0.75rem] text-cyan-200 hover:bg-cyan-400/[0.12]">
                    <UploadIcon size={15} /> Add Another Statement
                    <input
                      type="file"
                      accept=".pdf,.xls,.xlsx"
                      multiple={batchAvailable}
                      className="hidden"
                      onChange={(event) => {
                        addAutomaticFiles(Array.from(event.target.files || []));
                        event.target.value = '';
                      }}
                    />
                  </label>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right column: Needs Review panel */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-6 h-fit"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <h2 className="text-ink-muted text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 500 }}>Needs Review</h2>
              {(uploadReviewData?.items?.length || 0) > 0 && (
                <span className="px-1.5 py-0.5 text-[0.6rem] bg-amber-400/20 text-amber-200 rounded-full tabular-nums" style={{ fontWeight: 600 }}>
                  {uploadReviewData.items.length}
                </span>
              )}
            </div>
          </div>

          {!uploadReviewData?.items?.length ? (
            <div className="flex flex-col items-center py-8 text-ink-muted">
              <Check className="h-8 w-8 mb-2 text-emerald-200" />
              <p className="text-[0.85rem]" style={{ fontWeight: 400 }}>All classified!</p>
              <p className="text-[0.75rem] text-ink-muted">No uploaded transactions need review.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
              <AnimatePresence>
                {uploadReviewData.items.map((item) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -80 }}
                    className="rounded-[14px] bg-white/[0.04] border border-white/[0.08] overflow-hidden"
                  >
                    <div
                      onClick={() => setExpandedReviewId(expandedReviewId === item.id ? null : item.id)}
                      className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/[0.03] transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-7 h-7 rounded-[10px] bg-amber-400/[0.1] border border-amber-400/[0.12] flex items-center justify-center flex-shrink-0">
                          <AlertCircle className="h-3.5 w-3.5 text-amber-200" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-ink-secondary text-[0.8rem] truncate" style={{ fontWeight: 400 }}>{item.merchant_normalized || item.merchant_raw}</p>
                          <p className="text-ink-muted text-[0.65rem]">
                            {format(new Date(item.date), 'dd MMM yyyy')}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-[0.8rem] tabular-nums ${item.type === 'credit' ? 'text-emerald-200' : 'text-ink-secondary'}`} style={{ fontWeight: 500 }}>
                          {item.type === 'credit' ? '+' : '-'}{formatINR(item.amount)}
                        </span>
                        <ChevronDown className={`h-3 w-3 text-ink-muted transition-transform ${expandedReviewId === item.id ? 'rotate-180' : ''}`} />
                      </div>
                    </div>

                    <AnimatePresence>
                      {expandedReviewId === item.id && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="border-t border-white/[0.06]"
                        >
                          <div className="p-3 bg-white/[0.02]">
                            <p className="text-ink-muted text-[0.65rem] mb-2">Select a category:</p>
                            <div className="grid grid-cols-2 gap-1.5 mb-3">
                              {categories && Object.keys(categories).map((cat) => (
                                <button
                                  key={cat}
                                  onClick={() => {
                                    setReviewCategory(prev => ({ ...prev, [item.id]: cat }));
                                    setReviewSubcategory(prev => ({ ...prev, [item.id]: '' }));
                                  }}
                                  className={`px-2 py-1.5 text-[0.65rem] rounded-[8px] transition-all text-left ${
                                    reviewCategory[item.id] === cat
                                      ? 'bg-cyan-500/20 text-cyan-200 border border-cyan-400/30'
                                      : 'bg-white/[0.04] text-ink-muted border border-white/[0.06] hover:bg-white/[0.08]'
                                  }`}
                                  style={{ fontWeight: 500 }}
                                >
                                  {cat}
                                </button>
                              ))}
                            </div>

                            {reviewCategory[item.id] && categories[reviewCategory[item.id]] && (
                              <div className="mb-3">
                                <p className="text-ink-muted text-[0.65rem] mb-1.5">Subcategory (optional):</p>
                                <select
                                  aria-label={`Subcategory for ${item.merchant_normalized || item.merchant_raw}`}
                                  value={reviewSubcategory[item.id] || ''}
                                  onChange={(e) => setReviewSubcategory(prev => ({ ...prev, [item.id]: e.target.value }))}
                                  className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[8px] px-2 py-1.5 text-[0.7rem] text-ink-secondary focus:outline-none focus:border-cyan-400/30"
                                >
                                  <option value="" className="bg-[#1a2a4a]">No subcategory</option>
                                  {categories[reviewCategory[item.id]].map((sub) => (
                                    <option key={sub} value={sub} className="bg-[#1a2a4a]">{sub}</option>
                                  ))}
                                </select>
                              </div>
                            )}

                            {reviewCategory[item.id] && (
                              <GlassButton
                                onClick={() => {
                                  const category = reviewCategory[item.id];
                                  const subcategory = reviewSubcategory[item.id] || null;
                                  reviewResolveMutation.mutate({ transactionId: item.id, category, subcategory });
                                }}
                                disabled={reviewResolveMutation.isPending}
                                className="w-full justify-center"
                              >
                                {reviewResolveMutation.isPending ? 'Saving...' : 'Confirm'}
                              </GlassButton>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      </div>
        </>
      )}
    </div>
  );
}
