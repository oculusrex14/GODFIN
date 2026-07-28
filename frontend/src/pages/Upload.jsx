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
  previewStatement, reconcileStatement, importStatement,
  createIncomeSource, fetchReviewQueue, resolveReviewItem, fetchCategories,
} from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';

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

export default function UploadPage() {
  // Wizard state
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [password, setPassword] = useState('');
  const [reconcileData, setReconcileData] = useState(null);
  const [importResult, setImportResult] = useState(null);

  // Review panel state
  const [expandedReviewId, setExpandedReviewId] = useState(null);
  const [reviewCategory, setReviewCategory] = useState({});
  const [reviewSubcategory, setReviewSubcategory] = useState({});

  const queryClient = useQueryClient();

  // Step 1: Preview
  const previewMutation = useMutation({
    mutationFn: () => previewStatement(file, password || null),
    onSuccess: () => {
      setStep(2);
      // Auto-trigger reconcile
      reconcileMutation.mutate();
    },
  });

  // Step 2: Reconcile
  const reconcileMutation = useMutation({
    mutationFn: () => reconcileStatement(file, null, password || null),
    onSuccess: (data) => {
      setReconcileData(data);
    },
  });

  // Step 3: Import
  const importMutation = useMutation({
    mutationFn: () => importStatement(file, reconcileData?.account_id, {
      password: password || null,
      importNew: true,
      detectIncome: true,
    }),
    onSuccess: (data) => {
      setImportResult(data);
      setStep(3);
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      queryClient.invalidateQueries({ queryKey: ['reviewStats'] });
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
    },
  });

  // Review panel queries
  const { data: uploadReviewData } = useQuery({
    queryKey: ['uploadReviewQueue'],
    queryFn: () => fetchReviewQueue({ source: 'statement_upload', page_size: 50 }),
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
    const droppedFile = e.dataTransfer.files[0];
    const validation = validateFile(droppedFile);
    if (!validation.valid) {
      setFileError(validation.error);
      return;
    }
    setFileError('');
    setFile(droppedFile);
    resetResults();
  }

  function resetResults() {
    setStep(1);
    setReconcileData(null);
    setImportResult(null);
  }

  function handleReset() {
    setFile(null);
    setPassword('');
    resetResults();
  }

  const isProcessing = previewMutation.isPending || reconcileMutation.isPending || importMutation.isPending;

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Upload Statement</h1>
        <p className="text-white/30 text-[0.8rem]">Import transactions from bank statements</p>
      </motion.div>

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
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/30'
                : step > s.num
                  ? 'bg-emerald-500/10 text-emerald-400/70 border-emerald-400/20'
                  : 'bg-white/[0.04] text-white/30 border-white/[0.08]'
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
                <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider mb-4" style={{ fontWeight: 500 }}>Bank Statement</h2>

                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  className={`border-2 border-dashed rounded-[16px] p-8 text-center transition-all duration-300 ${
                    file ? 'border-emerald-400/20 bg-emerald-400/[0.03]' : 'border-white/[0.1] hover:border-white/[0.2]'
                  }`}
                >
                  {fileError && (
                    <p className="mb-2 text-rose-400 text-sm">{fileError}</p>
                  )}
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileText className="h-7 w-7 text-emerald-400/80" />
                      <div className="text-left">
                        <p className="text-white/80 text-[0.85rem]">{file.name}</p>
                        <p className="text-white/30 text-[0.7rem]">{(file.size / 1024).toFixed(1)} KB</p>
                      </div>
                      <button onClick={() => { setFile(null); resetResults(); }} className="ml-2 text-white/30 hover:text-rose-400/70">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ) : (
                    <label className="cursor-pointer">
                      <UploadIcon className="h-9 w-9 text-white/20 mx-auto mb-3" />
                      <p className="text-white/40 text-[0.85rem] mb-1">Drop a PDF or Excel file here, or click to browse</p>
                      <p className="text-white/20 text-[0.7rem]">HDFC Savings or Credit Card statement (PDF, XLS, XLSX)</p>
                      <input
                        type="file"
                        accept=".pdf,.xls,.xlsx"
                        onChange={(e) => {
                          setFileError('');
                          const selectedFile = e.target.files[0];
                          const validation = validateFile(selectedFile);
                          if (!validation.valid) {
                            setFileError(validation.error);
                            return;
                          }
                          setFile(selectedFile);
                          resetResults();
                        }}
                        className="hidden"
                      />
                    </label>
                  )}
                </div>

                {fileError && (
                  <p className="mt-2 text-rose-400 text-sm">{fileError}</p>
                )}

                {!isExcelFile(file) && (
                  <div className="mt-4">
                    <GlassInput type="password" placeholder="PDF password (if protected)" value={password} onChange={(e) => setPassword(e.target.value)} />
                  </div>
                )}

                <div className="mt-4">
                  <GlassButton
                    onClick={() => previewMutation.mutate()}
                    disabled={!file || isProcessing}
                    className="w-full justify-center"
                  >
                    {previewMutation.isPending ? (
                      <><Loader2 size={15} className="animate-spin" /> Parsing...</>
                    ) : (
                      <><FileCheck size={15} /> Upload & Reconcile</>
                    )}
                  </GlassButton>
                </div>

                {previewMutation.isError && (
                  <div className="mt-3 p-3 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                    <p className="text-rose-400/70 text-[0.8rem]">{previewMutation.error.message}</p>
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
                  <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 500 }}>Reconciliation Review</h2>
                  <button onClick={handleReset} className="text-white/30 hover:text-white/60 text-[0.7rem] flex items-center gap-1 transition-colors">
                    <ArrowLeft size={12} /> Start Over
                  </button>
                </div>

                {reconcileMutation.isPending ? (
                  <div className="flex flex-col items-center gap-3 py-8">
                    <Loader2 size={28} className="animate-spin text-cyan-400/60" />
                    <p className="text-white/40 text-[0.85rem]">Reconciling against existing records...</p>
                  </div>
                ) : reconcileMutation.isError ? (
                  <div className="p-4 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                    <p className="text-rose-400/70 text-[0.8rem] flex items-center gap-2">
                      <XCircle size={14} /> {reconcileMutation.error.message}
                    </p>
                    <button onClick={handleReset} className="mt-2 text-white/40 text-[0.75rem] hover:text-white/60">
                      Try again
                    </button>
                  </div>
                ) : reconcileData ? (
                  <>
                    {/* Summary counters */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                      {[
                        { label: 'Total Parsed', val: reconcileData.total_parsed, color: 'text-white/80' },
                        { label: 'Matched', val: reconcileData.matched_count, color: 'text-emerald-400/80' },
                        { label: 'Possible Dupes', val: reconcileData.possible_count, color: 'text-amber-400/80' },
                        { label: 'New', val: reconcileData.new_count, color: 'text-cyan-400/80' },
                      ].map((s) => (
                        <div key={s.label} className="text-center p-2 bg-white/[0.03] rounded-[12px]">
                          <p className={`text-[1.3rem] tabular-nums ${s.color}`} style={{ fontWeight: 300 }}>{s.val}</p>
                          <p className="text-white/30 text-[0.65rem]">{s.label}</p>
                        </div>
                      ))}
                    </div>

                    {/* New transactions list */}
                    {reconcileData.new_transactions?.length > 0 && (
                      <div className="mb-4">
                        <h3 className="text-cyan-400/70 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          New Transactions ({reconcileData.new_count})
                        </h3>
                        <div className="space-y-1 max-h-[200px] overflow-y-auto pr-1">
                          {reconcileData.new_transactions.map((t, i) => (
                            <div key={i} className="flex justify-between items-center text-[0.75rem] py-1.5 px-2 bg-white/[0.02] rounded-[8px]">
                              <div className="flex-1 min-w-0">
                                <span className="text-white/50 truncate block">{t.description}</span>
                                <span className="text-white/25 text-[0.65rem]">{t.date}</span>
                              </div>
                              <span className={`ml-2 tabular-nums ${t.type === 'credit' ? 'text-emerald-400/70' : 'text-white/60'}`}>
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
                        <h3 className="text-amber-400/70 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          <AlertTriangle className="h-3 w-3 inline mr-1" />
                          Possible Duplicates ({reconcileData.possible_count})
                        </h3>
                        <div className="space-y-1 max-h-[150px] overflow-y-auto pr-1">
                          {reconcileData.potential_duplicates.map((d, i) => (
                            <div key={i} className="text-[0.7rem] py-1.5 px-2 bg-amber-400/[0.03] rounded-[8px] border border-amber-400/[0.08]">
                              <div className="text-white/50">{d.parsed.description} — {formatINR(d.parsed.amount)}</div>
                              <div className="text-white/25">Matches: {d.existing.merchant} — {formatINR(d.existing.amount)} ({d.existing.date})</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Income detected */}
                    {reconcileData.income_detected?.length > 0 && (
                      <div className="mb-4 p-3 bg-emerald-400/[0.04] rounded-[12px] border border-emerald-400/[0.1]">
                        <h3 className="text-emerald-400/70 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                          <DollarSign className="h-3 w-3 inline mr-1" />
                          Income Detected ({reconcileData.income_count})
                        </h3>
                        <div className="space-y-1">
                          {reconcileData.income_detected.map((item, i) => (
                            <div key={i} className="flex justify-between text-[0.75rem]">
                              <span className="text-white/50">{item.description}</span>
                              <span className="text-emerald-400/70 tabular-nums">{formatINR(item.amount)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Import button / progress */}
                    {importMutation.isPending ? (
                      <div className="mt-2 p-4 bg-cyan-400/[0.04] rounded-[14px] border border-cyan-400/[0.12]">
                        <div className="flex items-center gap-3 mb-3">
                          <Loader2 size={20} className="animate-spin text-cyan-400/70" />
                          <div>
                            <p className="text-white/70 text-[0.85rem]" style={{ fontWeight: 500 }}>Importing transactions...</p>
                            <p className="text-white/30 text-[0.7rem]">Classifying and deduplicating {reconcileData.new_count} transactions</p>
                          </div>
                        </div>
                        <div className="w-full bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
                          <div className="h-full bg-cyan-400/50 rounded-full animate-pulse" style={{ width: '60%' }} />
                        </div>
                        <p className="text-white/20 text-[0.65rem] mt-2">This may take a moment. Other tabs remain usable.</p>
                      </div>
                    ) : (
                      <GlassButton
                        onClick={() => importMutation.mutate()}
                        disabled={reconcileData.new_count === 0}
                        className="w-full justify-center mt-2"
                      >
                        {reconcileData.new_count === 0 ? (
                          <>No new transactions to import</>
                        ) : (
                          <><ArrowRight size={15} /> Import {reconcileData.new_count} New Transactions</>
                        )}
                      </GlassButton>
                    )}

                    {importMutation.isError && (
                      <div className="mt-3 p-3 bg-rose-400/[0.06] border border-rose-400/[0.12] rounded-[12px]">
                        <p className="text-rose-400/70 text-[0.8rem]">{importMutation.error.message}</p>
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
                  <CheckCircle className="h-5 w-5 text-emerald-400/80" />
                  <h2 className="text-emerald-400/80 text-[0.85rem]" style={{ fontWeight: 500 }}>Import Complete</h2>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {[
                    { label: 'Total Parsed', val: importResult.total_parsed, color: 'text-white/80' },
                    { label: 'Matched (Skipped)', val: importResult.matched, color: 'text-emerald-400/80' },
                    { label: 'New Imported', val: importResult.new_imported, color: 'text-cyan-400/80' },
                    { label: 'Auto-Classified', val: importResult.classified, color: 'text-blue-400/80' },
                  ].map((s) => (
                    <div key={s.label} className="text-center p-2 bg-white/[0.03] rounded-[12px]">
                      <p className={`text-[1.3rem] tabular-nums ${s.color}`} style={{ fontWeight: 300 }}>{s.val}</p>
                      <p className="text-white/30 text-[0.65rem]">{s.label}</p>
                    </div>
                  ))}
                </div>

                {importResult.review_queue > 0 && (
                  <div className="mb-3 p-2.5 bg-amber-400/[0.05] rounded-[10px] border border-amber-400/[0.1]">
                    <p className="text-amber-400/70 text-[0.75rem]">
                      <AlertTriangle className="h-3 w-3 inline mr-1" />
                      {importResult.review_queue} transaction(s) need manual review
                    </p>
                  </div>
                )}

                {importResult.income_items?.length > 0 && (
                  <div className="mb-3 p-3 bg-emerald-400/[0.04] rounded-[12px] border border-emerald-400/[0.1]">
                    <h3 className="text-emerald-400/70 text-[0.75rem] mb-2" style={{ fontWeight: 500 }}>
                      <DollarSign className="h-3 w-3 inline mr-1" />
                      Income Detected ({importResult.income_detected})
                    </h3>
                    <div className="space-y-2">
                      {importResult.income_items.map((item, i) => (
                        <div key={i} className="flex items-center justify-between text-[0.75rem] p-2 bg-white/[0.02] rounded-[8px]">
                          <div className="flex-1 min-w-0">
                            <span className="text-white/50 block truncate">{item.description}</span>
                            <span className="text-emerald-400/70 tabular-nums">{formatINR(item.amount)}</span>
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
                            className="ml-2 px-2.5 py-1 text-[0.65rem] bg-emerald-500/20 text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition-colors whitespace-nowrap"
                          >
                            <Plus size={10} className="inline mr-0.5" /> Add as Income
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <GlassButton onClick={handleReset} className="w-full justify-center mt-2">
                  <UploadIcon size={15} /> Upload Another Statement
                </GlassButton>
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
              <h2 className="text-white/40 text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 500 }}>Needs Review</h2>
              {(uploadReviewData?.items?.length || 0) > 0 && (
                <span className="px-1.5 py-0.5 text-[0.6rem] bg-amber-400/20 text-amber-300 rounded-full tabular-nums" style={{ fontWeight: 600 }}>
                  {uploadReviewData.items.length}
                </span>
              )}
            </div>
          </div>

          {!uploadReviewData?.items?.length ? (
            <div className="flex flex-col items-center py-8 text-white/30">
              <Check className="h-8 w-8 mb-2 text-emerald-400/60" />
              <p className="text-[0.85rem]" style={{ fontWeight: 400 }}>All classified!</p>
              <p className="text-[0.75rem] text-white/20">No uploaded transactions need review.</p>
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
                          <AlertCircle className="h-3.5 w-3.5 text-amber-400/70" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-white/70 text-[0.8rem] truncate" style={{ fontWeight: 400 }}>{item.merchant_normalized || item.merchant_raw}</p>
                          <p className="text-white/25 text-[0.65rem]">
                            {format(new Date(item.date), 'dd MMM yyyy')}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-[0.8rem] tabular-nums ${item.type === 'credit' ? 'text-emerald-400/80' : 'text-white/60'}`} style={{ fontWeight: 500 }}>
                          {item.type === 'credit' ? '+' : '-'}{formatINR(item.amount)}
                        </span>
                        <ChevronDown className={`h-3 w-3 text-white/25 transition-transform ${expandedReviewId === item.id ? 'rotate-180' : ''}`} />
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
                            <p className="text-white/25 text-[0.65rem] mb-2">Select a category:</p>
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
                                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/30'
                                      : 'bg-white/[0.04] text-white/50 border border-white/[0.06] hover:bg-white/[0.08]'
                                  }`}
                                  style={{ fontWeight: 500 }}
                                >
                                  {cat}
                                </button>
                              ))}
                            </div>

                            {reviewCategory[item.id] && categories[reviewCategory[item.id]] && (
                              <div className="mb-3">
                                <p className="text-white/25 text-[0.65rem] mb-1.5">Subcategory (optional):</p>
                                <select
                                  value={reviewSubcategory[item.id] || ''}
                                  onChange={(e) => setReviewSubcategory(prev => ({ ...prev, [item.id]: e.target.value }))}
                                  className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[8px] px-2 py-1.5 text-[0.7rem] text-white/70 focus:outline-none focus:border-cyan-400/30"
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
    </div>
  );
}
