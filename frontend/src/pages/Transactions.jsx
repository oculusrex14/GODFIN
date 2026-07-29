import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { format } from 'date-fns';
import { Plus, ChevronLeft, ChevronRight, Pencil, Trash2, Search, LockKeyhole } from 'lucide-react';
import { Link, useSearchParams } from '../router';
import { fetchTransactions, deleteTransaction } from '../api/client';
import { GlassButton } from '../components/GlassButton';
import { GlassSelect } from '../components/GlassSelect';
import QuickAddModal from '../components/QuickAddModal';
import EditTransactionModal from '../components/EditTransactionModal';
import { useConfirm } from '../components/ConfirmDialog';
import { useTaxonomy } from '../hooks/useTaxonomy';
import { useAudit } from '../context/AuditContext';

function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

const CLASSIFICATION_LABELS = {
  transfer_detect: 'transfer detection',
  exact_match: 'exact merchant memory',
  confirmed_pattern: 'confirmed pattern',
  rule: 'deterministic rule',
  fuzzy: 'similar merchant memory',
  embedding: 'local similarity',
  personal_model: 'personal classifier',
  llm: 'AI suggestion',
  user: 'your correction',
  user_undo: 'restored after undo',
  narration_hint: 'statement parser',
};

const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Newest First' },
  { value: 'date_asc', label: 'Oldest First' },
  { value: 'amount_desc', label: 'Highest First' },
  { value: 'amount_asc', label: 'Lowest First' },
];

export default function Transactions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [addOpen, setAddOpen] = useState(false);
  const [editTxn, setEditTxn] = useState(null);
  const searchTimerRef = useRef(null);
  const pageSize = 20;
  const queryClient = useQueryClient();
  const { isAuditActive, activeAudit } = useAudit();
  const { confirm, ConfirmDialog: DeleteConfirmDialog } = useConfirm();
  const { categories, categoryNames } = useTaxonomy();

  const search = searchParams.get('q') || '';
  const effectiveSearch = search.trim().length >= 2 ? search.trim() : '';
  const categoryFilter = searchParams.get('category') || '';
  const subcategoryFilter = searchParams.get('subcategory') || '';
  const dateFrom = searchParams.get('date_from') || '';
  const dateTo = searchParams.get('date_to') || '';
  const sortOption = searchParams.get('sort') || 'date_desc';
  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1);

  useEffect(
    () => () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    },
    [],
  );

  function updateUrl(updates, { resetPage = true } = {}) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(updates)) {
        if (value == null || value === '' || value === 'date_desc') {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }
      if (resetPage) next.delete('page');
      return next;
    });
  }

  function handleSearchChange(value) {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      const trimmed = value.trim();
      updateUrl({ q: trimmed.length >= 2 ? trimmed : '' });
    }, 300);
  }

  // Parse sort option into sort_by and sort_order
  const [sortBy, sortOrder] = sortOption.split('_');

  const { data, isLoading } = useQuery({
    queryKey: ['transactions', { search: effectiveSearch, category: categoryFilter, subcategory: subcategoryFilter, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder, page, page_size: pageSize }],
    queryFn: () => fetchTransactions({
      search: effectiveSearch,
      category: categoryFilter,
      subcategory: subcategoryFilter,
      date_from: dateFrom,
      date_to: dateTo,
      sort_by: sortBy,
      sort_order: sortOrder,
      page,
      page_size: pageSize,
    }),
    placeholderData: (prevData) => prevData,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
    },
  });

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  async function handleDelete(txn) {
    const confirmed = await confirm({
      title: 'Delete Transaction',
      message: `Are you sure you want to delete "${txn.merchant_normalized || txn.merchant_raw}"?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (confirmed) {
      deleteMutation.mutate(txn.id);
    }
  }

  // Build category options from taxonomy
  const categoryOptions = [
    { value: '', label: 'All Categories' },
    ...categoryNames.map(cat => ({ value: cat, label: cat })),
  ];

  // Build subcategory options based on selected category
  const subcategoryOptions = [
    { value: '', label: 'All Subcategories' },
    ...(categoryFilter && categories[categoryFilter]
      ? categories[categoryFilter].map(sub => ({ value: sub, label: sub }))
      : []),
  ];

  return (
    <div>
      <DeleteConfirmDialog />
      <div className="flex items-center justify-between mb-5">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Transactions</h1>
          <p className="text-white/30 text-[0.8rem]">{data ? `${data.total} transaction${data.total !== 1 ? 's' : ''}` : '...'}</p>
        </motion.div>
        <GlassButton icon={<Plus size={15} />} onClick={() => setAddOpen(true)}>Add</GlassButton>
      </div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-wrap gap-3 mb-5"
      >
        <div className="relative flex-1 min-w-[200px] max-w-full">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20" aria-hidden="true" />
          <input
            key={search}
            defaultValue={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search merchants..."
            aria-label="Search merchants"
            className="w-full pl-9 pr-4 py-2.5 bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.12] rounded-[14px] text-white/80 text-[0.8rem] placeholder-white/20 focus:outline-none focus:border-cyan-400/30 transition-all"
          />
        </div>
        <GlassSelect
          value={categoryFilter}
          onChange={(v) => updateUrl({ category: v, subcategory: '' })}
          options={categoryOptions}
          aria-label="Filter by category"
        />
        {categoryFilter && (
          <GlassSelect
            value={subcategoryFilter}
            onChange={(v) => updateUrl({ subcategory: v })}
            options={subcategoryOptions}
            aria-label="Filter by subcategory"
          />
        )}
        <GlassSelect
          value={sortOption}
          onChange={(v) => updateUrl({ sort: v })}
          options={SORT_OPTIONS}
          aria-label="Sort transactions"
        />
        <input
          type="date"
          value={dateFrom}
          max={dateTo || undefined}
          onChange={(event) => updateUrl({ date_from: event.target.value })}
          aria-label="Transactions from date"
          className="min-h-11 rounded-[14px] bg-white/[0.06] border border-white/[0.12] px-3 text-white/55 text-xs outline-none focus:border-cyan-400/30"
        />
        <input
          type="date"
          value={dateTo}
          min={dateFrom || undefined}
          onChange={(event) => updateUrl({ date_to: event.target.value })}
          aria-label="Transactions to date"
          className="min-h-11 rounded-[14px] bg-white/[0.06] border border-white/[0.12] px-3 text-white/55 text-xs outline-none focus:border-cyan-400/30"
        />
        {(dateFrom || dateTo) && (
          <button
            onClick={() => updateUrl({ date_from: '', date_to: '' })}
            className="min-h-11 px-3 rounded-xl text-white/35 hover:text-white/60 hover:bg-white/[0.05] text-xs"
          >
            Clear dates
          </button>
        )}
        {isAuditActive && (
          <div className="flex items-center gap-1.5 px-3 py-2 bg-amber-500/10 border border-amber-400/20 rounded-[14px] text-amber-400/80 text-[0.7rem]">
            <Pencil size={11} aria-hidden="true" />
            Audit Active{activeAudit?.month ? ` (${activeAudit.month}/${activeAudit.year})` : ''}
          </div>
        )}
      </motion.div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]"
      >
        <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />

        {/* Desktop */}
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-[0.8rem]">
            <thead>
              <tr className="border-b border-white/[0.06]">
                <th className="text-left text-white/30 text-[0.65rem] uppercase tracking-wider px-5 py-3" style={{ fontWeight: 500 }}>Date</th>
                <th className="text-left text-white/30 text-[0.65rem] uppercase tracking-wider px-5 py-3" style={{ fontWeight: 500 }}>Merchant</th>
                <th className="text-right text-white/30 text-[0.65rem] uppercase tracking-wider px-5 py-3" style={{ fontWeight: 500 }}>Amount</th>
                <th className="text-left text-white/30 text-[0.65rem] uppercase tracking-wider px-5 py-3" style={{ fontWeight: 500 }}>Category</th>
                <th className="text-right text-white/30 text-[0.65rem] uppercase tracking-wider px-5 py-3" style={{ fontWeight: 500 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-white/30">Loading...</td></tr>
              ) : !data?.items?.length ? (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-white/30">No transactions found</td></tr>
              ) : (
                data.items.map((txn) => (
                  <tr key={txn.id} className="border-b border-white/[0.04] hover:bg-white/[0.03] transition-colors group">
                    <td className="px-5 py-3 text-white/50 tabular-nums">
                      {format(new Date(txn.date), 'dd MMM yyyy')}
                    </td>
                    <td className="px-5 py-3 text-white/80">
                      {txn.merchant_normalized || txn.merchant_raw}
                      {txn.subcategory && <span className="ml-2 text-white/20 text-[0.7rem]">({txn.subcategory})</span>}
                    </td>
                    <td className={`px-5 py-3 text-right tabular-nums ${txn.type === 'credit' ? 'text-emerald-400/80' : 'text-white/70'}`} style={{ fontWeight: 500 }}>
                      {txn.type === 'credit' ? '+' : '-'}{formatINR(txn.amount)}
                    </td>
                    <td className="px-5 py-3">
                      {txn.category ? (
                        <div>
                          <span className="inline-block px-2.5 py-0.5 bg-white/[0.06] rounded-[8px] text-white/50 text-[0.7rem] border border-white/[0.06]">
                            {txn.category}
                          </span>
                          {txn.classification_source && (
                            <p className="mt-1 text-white/22 text-[0.6rem]">
                              Why: {CLASSIFICATION_LABELS[txn.classification_source] || txn.classification_source}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="text-amber-400/70 text-[0.7rem]">Uncategorized</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {!txn.is_locked ? (
                        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => setEditTxn(txn)}
                            className="p-1.5 text-white/30 hover:text-white/70 hover:bg-white/[0.06] rounded-[8px] transition-colors"
                            title="Edit"
                            aria-label={`Edit transaction ${txn.merchant_normalized || txn.merchant_raw}`}
                          >
                            <Pencil size={13} aria-hidden="true" />
                          </button>
                          <button
                            onClick={() => handleDelete(txn)}
                            className="p-1.5 text-white/30 hover:text-rose-400/70 hover:bg-white/[0.06] rounded-[8px] transition-colors"
                            title="Delete"
                            aria-label={`Delete transaction ${txn.merchant_normalized || txn.merchant_raw}`}
                          >
                            <Trash2 size={13} aria-hidden="true" />
                          </button>
                        </div>
                      ) : (
                        <Link
                          to={`/audit?year=${txn.date.slice(0, 4)}&month=${Number(txn.date.slice(5, 7))}`}
                          className="inline-flex items-center gap-1 text-amber-300/60 hover:text-amber-200/80 text-[0.68rem]"
                          title="This month is finalized"
                        >
                          <LockKeyhole size={11} />
                          Reopen to edit
                        </Link>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile */}
        <div className="sm:hidden divide-y divide-white/[0.04]">
          {isLoading ? (
            <div className="px-5 py-8 text-center text-white/30">Loading...</div>
          ) : !data?.items?.length ? (
            <div className="px-5 py-8 text-center text-white/30">No transactions found</div>
          ) : (
            data.items.map((txn) => (
              <div key={txn.id} className="px-5 py-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-white/80 text-[0.85rem]" style={{ fontWeight: 500 }}>{txn.merchant_normalized || txn.merchant_raw}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-[0.85rem] tabular-nums ${txn.type === 'credit' ? 'text-emerald-400/80' : 'text-white/70'}`} style={{ fontWeight: 500 }}>
                      {txn.type === 'credit' ? '+' : '-'}{formatINR(txn.amount)}
                    </span>
                    {!txn.is_locked ? <>
                      <button onClick={() => setEditTxn(txn)} className="p-1 text-white/30 hover:text-white/70" aria-label={`Edit ${txn.merchant_normalized || txn.merchant_raw}`}><Pencil size={13} /></button>
                      <button onClick={() => handleDelete(txn)} className="p-1 text-white/30 hover:text-rose-400/70" aria-label={`Delete ${txn.merchant_normalized || txn.merchant_raw}`}><Trash2 size={13} /></button>
                    </> : (
                      <Link
                        to={`/audit?year=${txn.date.slice(0, 4)}&month=${Number(txn.date.slice(5, 7))}`}
                        className="p-1 text-amber-300/60"
                        aria-label="Reopen finalized month to edit"
                      >
                        <LockKeyhole size={13} />
                      </Link>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-[0.7rem] text-white/30">
                  <span>{format(new Date(txn.date), 'dd MMM')}</span>
                  {txn.category && <><span>·</span><span className="text-white/40">{txn.category}</span></>}
                  {txn.subcategory && <><span>·</span><span className="text-white/25">{txn.subcategory}</span></>}
                  {txn.classification_source && <><span>·</span><span className="text-white/20">{CLASSIFICATION_LABELS[txn.classification_source] || txn.classification_source}</span></>}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-white/[0.06]">
            <button
              onClick={() => updateUrl({ page: Math.max(1, page - 1) }, { resetPage: false })}
              disabled={page === 1}
              className="flex items-center gap-1 text-[0.8rem] text-white/40 hover:text-white/70 disabled:opacity-30 transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft size={15} aria-hidden="true" /> Prev
            </button>
            <span className="text-white/30 text-[0.8rem] tabular-nums">Page {page} of {totalPages}</span>
            <button
              onClick={() => updateUrl({ page: Math.min(totalPages, page + 1) }, { resetPage: false })}
              disabled={page === totalPages}
              className="flex items-center gap-1 text-[0.8rem] text-white/40 hover:text-white/70 disabled:opacity-30 transition-colors"
              aria-label="Next page"
            >
              Next <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        )}
      </motion.div>

      <QuickAddModal open={addOpen} onClose={() => setAddOpen(false)} />
      <EditTransactionModal
        key={editTxn?.id || 'closed'}
        open={!!editTxn}
        onClose={() => setEditTxn(null)}
        transaction={editTxn}
      />
    </div>
  );
}
