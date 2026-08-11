import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { updateTransaction } from '../api/client';
import { useTaxonomy } from '../hooks/useTaxonomy';
import DialogSurface from './DialogSurface';

export default function EditTransactionModal({ open, onClose, transaction }) {
  const [form, setForm] = useState(() => ({
    category: transaction?.category || '',
    subcategory: transaction?.subcategory || '',
    notes: transaction?.notes || '',
  }));
  const [error, setError] = useState('');
  const queryClient = useQueryClient();
  const { categories, categoryNames } = useTaxonomy();

  const mutation = useMutation({
    mutationFn: (data) => updateTransaction(transaction.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  function handleSubmit(e) {
    e.preventDefault();
    setError('');
    mutation.mutate({
      category: form.category || null,
      subcategory: form.subcategory || null,
      notes: form.notes || null,
    });
  }

  function set(key, value) {
    setForm((f) => {
      const next = { ...f, [key]: value };
      if (key === 'category') next.subcategory = '';
      return next;
    });
  }

  const subcategories = form.category ? categories[form.category] || [] : [];

  if (!transaction) return null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 z-50"
            onClick={onClose}
            data-godfin-dialog-backdrop="true"
            aria-hidden="true"
          />
          <DialogSurface
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            labelledBy="edit-transaction-title"
            onClose={onClose}
            className="fixed inset-x-4 bottom-4 top-auto sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-full sm:max-w-md bg-slate-800 border border-slate-700 rounded-2xl z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
              <h2 id="edit-transaction-title" className="text-base font-semibold text-white">Edit Transaction</h2>
              <button onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close edit transaction dialog">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="px-5 pt-4 pb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-white font-medium">
                  {transaction.merchant_normalized || transaction.merchant_raw}
                </span>
                <span className={`text-sm font-medium tabular-nums ${
                  transaction.type === 'credit' ? 'text-emerald-400' : 'text-white'
                }`}>
                  {transaction.type === 'credit' ? '+' : '-'}
                  {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 }).format(transaction.amount)}
                </span>
              </div>
              <p className="text-xs text-slate-500">{transaction.date}</p>
            </div>

            <form onSubmit={handleSubmit} className="p-5 pt-2 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="edit-transaction-category" className="block text-xs text-slate-400 mb-1">Category</label>
                  <select
                    id="edit-transaction-category"
                    value={form.category}
                    onChange={(e) => set('category', e.target.value)}
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 focus:border-emerald-400 focus:outline-none"
                  >
                    <option value="">-- None --</option>
                    {categoryNames.map((cat) => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="edit-transaction-subcategory" className="block text-xs text-slate-400 mb-1">Subcategory</label>
                  <select
                    id="edit-transaction-subcategory"
                    value={form.subcategory}
                    onChange={(e) => set('subcategory', e.target.value)}
                    disabled={!form.category}
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 focus:border-emerald-400 focus:outline-none disabled:opacity-40"
                  >
                    <option value="">-- None --</option>
                    {subcategories.map((sub) => (
                      <option key={sub} value={sub}>{sub}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="edit-transaction-notes" className="block text-xs text-slate-400 mb-1">Notes</label>
                <input
                  id="edit-transaction-notes"
                  type="text"
                  value={form.notes}
                  onChange={(e) => set('notes', e.target.value)}
                  placeholder="Optional"
                  className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
                />
              </div>

              {error && <p className="text-rose-400 text-sm" role="alert">{error}</p>}

              <button
                type="submit"
                disabled={mutation.isPending}
                className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-500/50 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {mutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </form>
          </DialogSurface>
        </>
      )}
    </AnimatePresence>
  );
}
