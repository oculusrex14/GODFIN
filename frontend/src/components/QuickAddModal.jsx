import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { createTransaction, fetchAccounts } from '../api/client';
import { useTaxonomy } from '../hooks/useTaxonomy';
import DialogSurface from './DialogSurface';

const INITIAL = {
  date: format(new Date(), 'yyyy-MM-dd'),
  merchant_raw: '',
  amount: '',
  type: 'debit',
  account_id: '',
  category: '',
  subcategory: '',
  notes: '',
};

export default function QuickAddModal({ open, onClose }) {
  const [form, setForm] = useState(INITIAL);
  const [error, setError] = useState('');
  const queryClient = useQueryClient();
  const { categories, categoryNames } = useTaxonomy();

  const { data: accounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    enabled: open,
  });

  const mutation = useMutation({
    mutationFn: createTransaction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      setForm(INITIAL);
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!form.merchant_raw || !form.amount) {
      setError('Merchant and amount are required');
      return;
    }
    const payload = {
      ...form,
      account_id: form.account_id || accounts?.[0]?.id,
      amount: parseFloat(form.amount),
      category: form.category || null,
      subcategory: form.subcategory || null,
      notes: form.notes || null,
    };
    mutation.mutate(payload);
  }

  function set(key, value) {
    setForm((f) => {
      const next = { ...f, [key]: value };
      if (key === 'category') next.subcategory = '';
      return next;
    });
  }

  const subcategories = form.category ? categories[form.category] || [] : [];

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
            labelledBy="quick-add-title"
            onClose={onClose}
            className="fixed inset-x-4 bottom-4 top-auto sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-full sm:max-w-md bg-slate-800 border border-slate-700 rounded-2xl z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
              <h2 id="quick-add-title" className="text-base font-semibold text-white">Add Transaction</h2>
              <button onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close add transaction dialog">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="quick-add-date" className="block text-xs text-slate-400 mb-1">Date</label>
                  <input
                    id="quick-add-date"
                    type="date"
                    value={form.date}
                    onChange={(e) => set('date', e.target.value)}
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 focus:border-emerald-400 focus:outline-none"
                  />
                </div>
                <div>
                  <span id="quick-add-type-label" className="block text-xs text-slate-400 mb-1">Type</span>
                  <div className="flex rounded-lg overflow-hidden border border-slate-600" role="group" aria-labelledby="quick-add-type-label">
                    {['debit', 'credit'].map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => set('type', t)}
                        aria-pressed={form.type === t}
                        className={`flex-1 py-2 text-sm capitalize transition-colors ${
                          form.type === t
                            ? t === 'debit'
                              ? 'bg-rose-500/20 text-rose-400'
                              : 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-slate-700/50 text-slate-400'
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label htmlFor="quick-add-merchant" className="block text-xs text-slate-400 mb-1">Merchant</label>
                <input
                  id="quick-add-merchant"
                  type="text"
                  value={form.merchant_raw}
                  onChange={(e) => set('merchant_raw', e.target.value)}
                  placeholder="e.g. Swiggy, Amazon"
                  className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
                />
              </div>

              <div>
                <label htmlFor="quick-add-amount" className="block text-xs text-slate-400 mb-1">Amount</label>
                <input
                  id="quick-add-amount"
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.amount}
                  onChange={(e) => set('amount', e.target.value)}
                  placeholder="0.00"
                  className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none tabular-nums"
                />
              </div>

              <div>
                <label htmlFor="quick-add-account" className="block text-xs text-slate-400 mb-1">Account</label>
                <select
                  id="quick-add-account"
                  value={form.account_id || accounts?.[0]?.id || ''}
                  onChange={(e) => set('account_id', e.target.value)}
                  className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 focus:border-emerald-400 focus:outline-none"
                >
                  {accounts?.map((acc) => (
                    <option key={acc.id} value={acc.id}>{acc.nickname}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="quick-add-category" className="block text-xs text-slate-400 mb-1">Category</label>
                  <select
                    id="quick-add-category"
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
                  <label htmlFor="quick-add-subcategory" className="block text-xs text-slate-400 mb-1">Subcategory</label>
                  <select
                    id="quick-add-subcategory"
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
                <label htmlFor="quick-add-notes" className="block text-xs text-slate-400 mb-1">Notes</label>
                <input
                  id="quick-add-notes"
                  type="text"
                  value={form.notes}
                  onChange={(e) => set('notes', e.target.value)}
                  placeholder="Optional"
                  className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
                />
              </div>

              {error && (
                <p className="text-rose-400 text-sm" role="alert">{error}</p>
              )}

              <button
                type="submit"
                disabled={mutation.isPending}
                className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-500/50 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {mutation.isPending ? 'Adding...' : 'Add Transaction'}
              </button>
            </form>
          </DialogSurface>
        </>
      )}
    </AnimatePresence>
  );
}
