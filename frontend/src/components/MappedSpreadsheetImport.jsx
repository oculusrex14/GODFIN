import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle,
  FileCheck,
  FileSpreadsheet,
  Loader2,
  Trash2,
  Upload,
} from 'lucide-react';

import {
  fetchAccounts,
  importMappedSpreadsheet,
  inspectMappedSpreadsheet,
  previewMappedSpreadsheet,
} from '../api/client';
import { useToast } from '../context/ToastContext';
import { GlassButton } from './GlassButton';

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const REQUIRED_FIELDS = [
  ['date_column', 'Transaction date'],
  ['description_column', 'Description or narration'],
  ['debit_column', 'Money out (debit)'],
  ['credit_column', 'Money in (credit)'],
];
const OPTIONAL_FIELDS = [
  ['value_date_column', 'Value date'],
  ['reference_column', 'Reference number'],
  ['running_balance_column', 'Balance after transaction'],
  ['account_identifier_column', 'Account or card number'],
];
const DATE_FORMATS = [
  ['dd/mm/yyyy', 'Day / month / year — 31/01/2026'],
  ['dd-mm-yyyy', 'Day - month - year — 31-01-2026'],
  ['yyyy-mm-dd', 'Year - month - day — 2026-01-31'],
  ['mm/dd/yyyy', 'Month / day / year — 01/31/2026'],
  ['auto', 'Detect automatically (reject unclear dates)'],
];

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function accountLabel(account) {
  return account.nickname
    || `${account.bank} ${account.account_type.replaceAll('_', ' ')} ••••${account.last_4_digits}`;
}

function newQueueEntry(file) {
  return {
    id: fileKey(file),
    file,
    stage: 'waiting',
    inspect: null,
    mapping: null,
    accountId: '',
    dateFormat: 'dd/mm/yyyy',
    preview: null,
    result: null,
    error: '',
  };
}

function validateFiles(files) {
  const accepted = [];
  const rejected = [];
  for (const file of files) {
    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.csv') && !lower.endsWith('.xlsx')) {
      rejected.push(`${file.name}: choose a CSV or XLSX file.`);
    } else if (file.size > MAX_FILE_SIZE) {
      rejected.push(`${file.name}: file must be smaller than 10 MB.`);
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}

function mappingStorageKey(headerSignature) {
  return `godfin:mapped-import:${headerSignature}`;
}

function savedMapping(headerSignature) {
  try {
    const value = window.localStorage.getItem(mappingStorageKey(headerSignature));
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function ColumnSelect({ field, label, value, columns, optional, onChange }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[0.68rem] text-ink-muted">{label}{optional ? ' (optional)' : ''}</span>
      <select
        aria-label={label}
        value={value ?? ''}
        onChange={(event) => onChange(
          event.target.value === '' ? null : Number(event.target.value),
        )}
        className="rounded-[10px] border border-white/[0.12] bg-[#15294a] px-3 py-2 text-[0.75rem] text-ink-secondary focus:border-cyan-400/40 focus:outline-none"
      >
        <option value="">{optional ? 'Not included' : 'Select a column'}</option>
        {columns.map(column => (
          <option key={`${field}-${column.index}`} value={column.index}>
            {column.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function MappedSpreadsheetImport() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [queue, setQueue] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [fileError, setFileError] = useState('');
  const [reviewAllFirst, setReviewAllFirst] = useState(true);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
  });
  const active = queue.find(item => item.id === activeId) || queue[0] || null;
  const activeAccounts = useMemo(
    () => accounts.filter(account => account.is_active !== false),
    [accounts],
  );

  const updateEntry = (id, patch) => {
    setQueue(current => current.map(item => (
      item.id === id ? { ...item, ...patch } : item
    )));
  };

  const inspectMutation = useMutation({
    mutationFn: entry => inspectMappedSpreadsheet(entry.file),
    onMutate: entry => updateEntry(entry.id, { stage: 'inspecting', error: '' }),
    onSuccess: (data, entry) => {
      const previous = savedMapping(data.header_signature);
      updateEntry(entry.id, {
        stage: 'mapping',
        inspect: data,
        mapping: previous?.mapping || data.suggested_mapping,
        dateFormat: previous?.dateFormat || 'dd/mm/yyyy',
        accountId: entry.accountId || activeAccounts[0]?.id || '',
        preview: null,
        result: null,
      });
    },
    onError: (error, entry) => updateEntry(entry.id, {
      stage: 'failed',
      error: error?.message || 'GODFIN could not inspect this spreadsheet.',
    }),
  });

  const previewMutation = useMutation({
    mutationFn: entry => previewMappedSpreadsheet(
      entry.file,
      entry.accountId,
      entry.mapping,
      entry.dateFormat,
    ),
    onMutate: entry => updateEntry(entry.id, { stage: 'previewing', error: '' }),
    onSuccess: (data, entry) => {
      try {
        window.localStorage.setItem(
          mappingStorageKey(data.header_signature),
          JSON.stringify({ mapping: entry.mapping, dateFormat: entry.dateFormat }),
        );
      } catch {
        // Saving a convenience preference must never block the import.
      }
      updateEntry(entry.id, {
        stage: data.status === 'ready' ? 'reviewed' : 'mapping',
        preview: data,
      });
    },
    onError: (error, entry) => updateEntry(entry.id, {
      stage: 'mapping',
      error: error?.message || 'GODFIN could not preview this mapping.',
    }),
  });

  const importMutation = useMutation({
    mutationFn: entry => importMappedSpreadsheet(
      entry.file,
      entry.accountId,
      entry.mapping,
      entry.dateFormat,
      entry.preview,
    ),
    onMutate: entry => updateEntry(entry.id, { stage: 'importing', error: '' }),
    onSuccess: async (data, entry) => {
      updateEntry(entry.id, { stage: 'complete', result: data });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['transactions'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboardStats'] }),
        queryClient.invalidateQueries({ queryKey: ['reviewQueue'] }),
      ]);
      addToast(`${data.imported} transaction(s) imported from ${entry.file.name}.`, 'success');
    },
    onError: (error, entry) => updateEntry(entry.id, {
      stage: 'reviewed',
      error: error?.message || 'No transactions were imported.',
    }),
  });

  const addFiles = (incoming) => {
    const { accepted, rejected } = validateFiles(Array.from(incoming));
    const existing = new Set(queue.map(item => item.id));
    const additions = accepted
      .map(newQueueEntry)
      .filter(item => !existing.has(item.id));
    setQueue(current => [...current, ...additions]);
    if (additions.length && (!activeId || active?.stage === 'complete')) {
      setActiveId(additions[0].id);
    }
    setFileError(rejected.join(' '));
  };

  const removeEntry = (id) => {
    if (inspectMutation.isPending || previewMutation.isPending || importMutation.isPending) return;
    const index = queue.findIndex(item => item.id === id);
    const remaining = queue.filter(item => item.id !== id);
    setQueue(remaining);
    if (activeId === id) {
      setActiveId(remaining[Math.min(index, remaining.length - 1)]?.id || null);
    }
  };

  const setMapping = (field, value) => {
    if (!active) return;
    updateEntry(active.id, {
      mapping: { ...active.mapping, [field]: value },
      preview: null,
      result: null,
      stage: 'mapping',
    });
  };

  const requiredReady = active?.mapping
    && REQUIRED_FIELDS.every(([field]) => Number.isInteger(active.mapping[field]));
  const completeCount = queue.filter(item => item.stage === 'complete').length;
  const reviewedCount = queue.filter(item => item.stage === 'reviewed').length;
  const failedCount = queue.filter(item => item.stage === 'failed').length;
  const allReviewed = queue.length > 0 && queue.every(
    item => ['reviewed', 'complete'].includes(item.stage),
  );
  const totals = queue.reduce((summary, item) => ({
    imported: summary.imported + (item.result?.imported || 0),
    duplicates: summary.duplicates + (item.result?.skipped_duplicate || 0),
    review: summary.review + (item.result?.review_queue || 0),
  }), { imported: 0, duplicates: 0, review: 0 });
  const busy = inspectMutation.isPending || previewMutation.isPending || importMutation.isPending;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(220px,0.38fr)_minmax(0,1fr)]">
      <section className="relative overflow-hidden rounded-[20px] border border-white/[0.18] bg-white/[0.08] p-5 backdrop-blur-[24px]">
        <div className="mb-4">
          <h2 className="text-[0.75rem] font-medium uppercase tracking-wider text-ink-muted">Import queue</h2>
          <p className="mt-1 text-[0.7rem] leading-relaxed text-ink-muted">
            Add several files, then inspect and confirm them one at a time. Nothing is imported during preview.
          </p>
        </div>
        <label
          className="block cursor-pointer rounded-[14px] border border-dashed border-cyan-400/20 bg-cyan-400/[0.04] p-4 text-center hover:bg-cyan-400/[0.07]"
          onDragOver={event => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            addFiles(event.dataTransfer.files || []);
          }}
        >
          <Upload className="mx-auto mb-2 h-6 w-6 text-cyan-200" />
          <span className="text-[0.78rem] text-ink-secondary">Choose CSV or XLSX files</span>
          <span className="mt-1 block text-[0.65rem] text-ink-muted">Up to 10 MB each · one transaction sheet per XLSX</span>
          <input
            className="hidden"
            type="file"
            accept=".csv,.xlsx"
            multiple
            onChange={(event) => {
              addFiles(event.target.files || []);
              event.target.value = '';
            }}
          />
        </label>
        {fileError && <p className="mt-2 text-[0.7rem] text-rose-200">{fileError}</p>}

        {queue.length > 0 && (
          <div className="mt-4 space-y-2">
            <div className="flex justify-between text-[0.65rem] text-ink-muted">
              <span>{queue.length} file(s)</span>
              <span>{reviewedCount} reviewed · {completeCount} complete · {failedCount} failed</span>
            </div>
            {queue.map(item => (
              <div
                key={item.id}
                className={`flex w-full items-center rounded-[12px] border text-left transition-colors ${
                  active?.id === item.id
                    ? 'border-cyan-400/30 bg-cyan-400/[0.08]'
                    : 'border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06]'
                }`}
              >
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setActiveId(item.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 p-2.5 text-left disabled:cursor-not-allowed"
                >
                  {item.stage === 'complete' ? (
                    <CheckCircle className="h-4 w-4 shrink-0 text-emerald-200" />
                  ) : item.stage.endsWith('ing') ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-cyan-200" />
                  ) : item.stage === 'failed' ? (
                    <AlertTriangle className="h-4 w-4 shrink-0 text-rose-200" />
                  ) : (
                    <FileSpreadsheet className="h-4 w-4 shrink-0 text-ink-muted" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.72rem] text-ink-secondary">{item.file.name}</span>
                    <span className="block text-[0.6rem] capitalize text-ink-muted">{item.stage}</span>
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${item.file.name}`}
                  disabled={busy}
                  onClick={() => removeEntry(item.id)}
                  className="mr-2 rounded p-1 text-ink-muted hover:text-rose-200 disabled:cursor-not-allowed"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            <label className="flex items-center gap-2 pt-1 text-[0.64rem] leading-relaxed text-ink-muted">
              <input
                type="checkbox"
                checked={reviewAllFirst}
                onChange={event => setReviewAllFirst(event.target.checked)}
                className="accent-cyan-400"
              />
              Review every queued file before importing any of them
            </label>
            {(completeCount > 0 || failedCount > 0) && (
              <p className="pt-1 text-[0.62rem] leading-relaxed text-ink-muted">
                Batch summary: {totals.imported} imported · {totals.duplicates} duplicates skipped · {totals.review} need category review · {failedCount} failed
              </p>
            )}
          </div>
        )}
      </section>

      <section className="relative min-h-[320px] overflow-hidden rounded-[20px] border border-white/[0.18] bg-white/[0.08] p-6 backdrop-blur-[24px]">
        {!active ? (
          <div className="flex min-h-[270px] flex-col items-center justify-center text-center">
            <FileSpreadsheet className="mb-3 h-10 w-10 text-ink-muted" />
            <p className="text-[0.85rem] text-ink-muted">Add a spreadsheet to begin</p>
            <p className="mt-1 max-w-md text-[0.7rem] leading-relaxed text-ink-muted">
              GODFIN will show the columns and sample rows before asking what each column means.
            </p>
          </div>
        ) : active.stage === 'waiting' || active.stage === 'failed' || active.stage === 'inspecting' ? (
          <div className="flex min-h-[270px] flex-col items-center justify-center text-center">
            <FileCheck className="mb-3 h-9 w-9 text-cyan-200" />
            <h3 className="max-w-md truncate text-[0.9rem] text-ink-secondary">{active.file.name}</h3>
            <p className="mt-2 max-w-md text-[0.72rem] leading-relaxed text-ink-muted">
              Inspecting reads the headings and a few sample rows locally. It does not save any transactions.
            </p>
            {active.error && <p className="mt-3 max-w-md text-[0.72rem] text-rose-200">{active.error}</p>}
            <GlassButton
              className="mt-5 justify-center"
              disabled={busy}
              onClick={() => inspectMutation.mutate(active)}
            >
              {active.stage === 'inspecting' ? <><Loader2 size={14} className="animate-spin" /> Inspecting…</> : 'Inspect columns'}
            </GlassButton>
          </div>
        ) : (
          <div>
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-[0.95rem] text-ink-secondary">Tell GODFIN what each column means</h3>
                <p className="mt-1 text-[0.68rem] text-ink-muted">
                  Header row {active.inspect.header_row} · {active.inspect.row_count.toLocaleString('en-IN')} transaction row(s)
                </p>
              </div>
              {active.stage === 'complete' && (
                <span className="flex items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-3 py-1 text-[0.68rem] text-emerald-200">
                  <CheckCircle size={12} /> Imported
                </span>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5">
                <span className="text-[0.68rem] text-ink-muted">Import into account</span>
                <select
                  value={active.accountId}
                  onChange={event => updateEntry(active.id, {
                    accountId: event.target.value,
                    preview: null,
                    result: null,
                    stage: 'mapping',
                  })}
                  className="rounded-[10px] border border-white/[0.12] bg-[#15294a] px-3 py-2 text-[0.75rem] text-ink-secondary focus:border-cyan-400/40 focus:outline-none"
                >
                  <option value="">Select an account</option>
                  {activeAccounts.map(account => (
                    <option key={account.id} value={account.id}>{accountLabel(account)}</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1.5">
                <span className="text-[0.68rem] text-ink-muted">Date style used in this file</span>
                <select
                  value={active.dateFormat}
                  onChange={event => updateEntry(active.id, {
                    dateFormat: event.target.value,
                    preview: null,
                    result: null,
                    stage: 'mapping',
                  })}
                  className="rounded-[10px] border border-white/[0.12] bg-[#15294a] px-3 py-2 text-[0.75rem] text-ink-secondary focus:border-cyan-400/40 focus:outline-none"
                >
                  {DATE_FORMATS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {REQUIRED_FIELDS.map(([field, label]) => (
                <ColumnSelect
                  key={field}
                  field={field}
                  label={label}
                  value={active.mapping?.[field]}
                  columns={active.inspect.columns}
                  onChange={value => setMapping(field, value)}
                />
              ))}
              {OPTIONAL_FIELDS.map(([field, label]) => (
                <ColumnSelect
                  key={field}
                  field={field}
                  label={label}
                  value={active.mapping?.[field]}
                  columns={active.inspect.columns}
                  optional
                  onChange={value => setMapping(field, value)}
                />
              ))}
            </div>

            <div className="mt-5 overflow-x-auto rounded-[12px] border border-white/[0.08]">
              <table className="min-w-full text-left text-[0.67rem]">
                <thead className="bg-white/[0.05] text-ink-muted">
                  <tr>{active.inspect.columns.map(column => <th key={column.index} className="whitespace-nowrap px-3 py-2 font-medium">{column.label}</th>)}</tr>
                </thead>
                <tbody className="text-ink-muted">
                  {active.inspect.sample_rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="border-t border-white/[0.05]">
                      {active.inspect.columns.map(column => <td key={column.index} className="max-w-[220px] truncate whitespace-nowrap px-3 py-2">{row[column.index] || '—'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {active.preview && (
              <div className={`mt-4 rounded-[12px] border p-3 ${
                active.preview.status === 'ready'
                  ? 'border-emerald-400/15 bg-emerald-400/[0.05]'
                  : 'border-amber-400/15 bg-amber-400/[0.05]'
              }`}>
                {active.preview.status === 'ready' ? (
                  <>
                    <p className="flex items-center gap-2 text-[0.75rem] text-emerald-200">
                      <CheckCircle size={14} /> Ready: {active.preview.new_count} new transaction(s), {active.preview.matched_count} exact duplicate(s)
                    </p>
                    <p className="mt-1 text-[0.68rem] leading-relaxed text-ink-muted">
                      {active.preview.balance_controls_verified
                        ? 'The debit, credit, and running-balance arithmetic agree. A verified account balance can be shown after import.'
                        : 'Transactions can be imported, but no verified account balance will be claimed because a running-balance column was not mapped.'}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="flex items-center gap-2 text-[0.75rem] text-amber-200"><AlertTriangle size={14} /> Fix the rows below, then preview again</p>
                    <ul className="mt-2 space-y-1 text-[0.68rem] text-ink-muted">
                      {active.preview.errors.map(error => <li key={`${error.row}-${error.code}`}>Row {error.row}: {error.message}</li>)}
                    </ul>
                  </>
                )}
              </div>
            )}
            {active.result && (
              <div className="mt-4 rounded-[12px] border border-emerald-400/15 bg-emerald-400/[0.05] p-3 text-[0.72rem] text-emerald-200">
                Imported {active.result.imported} transaction(s); skipped {active.result.skipped_duplicate} exact duplicate(s). {active.result.review_queue} item(s) need your category review.
              </div>
            )}
            {active.error && <p className="mt-3 text-[0.72rem] text-rose-200">{active.error}</p>}

            {active.stage !== 'complete' && (
              <div className="mt-5 flex flex-wrap justify-end gap-2">
                <GlassButton
                  disabled={!requiredReady || !active.accountId || busy}
                  onClick={() => previewMutation.mutate(active)}
                >
                  {active.stage === 'previewing' ? <><Loader2 size={14} className="animate-spin" /> Previewing…</> : <><FileCheck size={14} /> Preview safely</>}
                </GlassButton>
                {['reviewed', 'importing'].includes(active.stage) && active.preview?.status === 'ready' && (
                  <GlassButton
                    disabled={busy || (reviewAllFirst && !allReviewed)}
                    onClick={() => importMutation.mutate(active)}
                  >
                    {active.stage === 'importing'
                      ? <><Loader2 size={14} className="animate-spin" /> Importing…</>
                      : reviewAllFirst && !allReviewed
                        ? <>Review remaining files first</>
                        : <>Confirm and import</>}
                  </GlassButton>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
