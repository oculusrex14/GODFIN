import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  KeyRound,
  Landmark,
  Pencil,
  Plus,
  RefreshCw,
  Scale,
  Trash2,
  WalletCards,
  X,
} from 'lucide-react';

import {
  configureMarketData,
  createNetWorthItem,
  deleteNetWorthItem,
  fetchLicenseStatus,
  fetchMarketDataStatus,
  fetchNetWorth,
  refreshNetWorthQuote,
  restoreNetWorthItem,
  updateNetWorthItem,
} from '../api/client';
import CalculationInfo from '../components/CalculationInfo';
import { GlassButton } from '../components/GlassButton';
import { GlassInput } from '../components/GlassInput';
import { GlassSelect } from '../components/GlassSelect';
import DialogSurface from '../components/DialogSurface';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';

const INITIAL_FORM = {
  name: '',
  item_type: 'asset',
  asset_class: 'cash',
  valuation_mode: 'manual',
  symbol: '',
  quantity: '1',
  currency: 'INR',
  manual_value: '',
  valuation_source: '',
  source_url: '',
  valued_at: '',
  expires_on: '',
  notes: '',
};

const ASSET_CLASSES = [
  'cash', 'stock', 'etf', 'mutual_fund', 'crypto', 'bond', 'metal',
  'property', 'land', 'gem', 'private_asset', 'debt', 'other',
];

function money(value, currency = 'INR') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return 'Unavailable';
  }
  return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function freshness(item) {
  if (!item.available) return { label: 'Needs review', width: 100, tone: 'bg-amber-400/70' };
  if (!item.expires_on) return { label: 'No expiry set', width: 25, tone: 'bg-white/20' };
  const expires = new Date(`${item.expires_on}T23:59:59`);
  const days = Math.ceil((expires - new Date()) / 86400000);
  if (item.stale || days < 0) return { label: 'Valuation expired', width: 100, tone: 'bg-rose-400/70' };
  const width = Math.max(10, Math.min(100, (days / 30) * 100));
  return {
    label: `${days} day${days === 1 ? '' : 's'} until review`,
    width,
    tone: days <= 7 ? 'bg-amber-400/70' : 'bg-emerald-400/60',
  };
}

export default function NetWorth() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [editingId, setEditingId] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [baseCurrency, setBaseCurrency] = useState('');
  const [recentDeletion, setRecentDeletion] = useState(null);
  const undoRef = useRef(null);
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { confirm, ConfirmDialog: ConfirmDialogComponent } = useConfirm();
  const { data: license } = useQuery({ queryKey: ['license'], queryFn: fetchLicenseStatus });
  const entitled = license?.features?.includes('net_worth');
  const { data: summary } = useQuery({
    queryKey: ['netWorth'],
    queryFn: fetchNetWorth,
    enabled: Boolean(entitled),
  });
  const { data: marketData } = useQuery({
    queryKey: ['marketDataStatus'],
    queryFn: fetchMarketDataStatus,
    enabled: Boolean(entitled),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['netWorth'] });
  const saveMutation = useMutation({
    mutationFn: data => (
      editingId
        ? updateNetWorthItem({ id: editingId, ...data })
        : createNetWorthItem(data)
    ),
    onSuccess: () => {
      refresh();
      setForm(INITIAL_FORM);
      setEditingId(null);
      setOpen(false);
      addToast('Net-worth item saved locally.', 'success');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: item => deleteNetWorthItem(item.id).then(result => ({ ...result, item })),
    onSuccess: result => {
      setRecentDeletion(result);
      refresh();
      addToast('Net-worth item removed. You can undo this change.', 'info');
    },
  });
  const restoreMutation = useMutation({
    mutationFn: restoreNetWorthItem,
    onSuccess: () => {
      setRecentDeletion(null);
      refresh();
      addToast('Net-worth item restored.', 'success');
    },
  });
  const quoteMutation = useMutation({
    mutationFn: refreshNetWorthQuote,
    onSuccess: () => {
      refresh();
      addToast('Live quote and provenance saved.', 'success');
    },
  });
  const configMutation = useMutation({
    mutationFn: configureMarketData,
    onSuccess: data => {
      queryClient.setQueryData(['marketDataStatus'], data);
      refresh();
      setApiKey('');
      setBaseCurrency('');
      if (data.quotes_requiring_refresh > 0) {
        addToast(
          `Base currency saved. Refresh ${data.quotes_requiring_refresh} market quote${data.quotes_requiring_refresh === 1 ? '' : 's'} before totals return.`,
          'info',
        );
      } else {
        addToast('Market-data settings and verified currency rates saved locally.', 'success');
      }
    },
  });
  const grouped = useMemo(() => ({
    assets: summary?.items?.filter(item => item.item_type === 'asset') || [],
    liabilities: summary?.items?.filter(item => item.item_type === 'liability') || [],
  }), [summary]);

  useEffect(() => {
    if (recentDeletion) undoRef.current?.focus();
  }, [recentDeletion]);

  const requestDelete = async (item) => {
    const quoteCount = item.quote_history?.length || 0;
    const confirmed = await confirm({
      title: `Remove ${item.name}?`,
      message: `This will hide 1 item${quoteCount ? ` and ${quoteCount} saved quote${quoteCount === 1 ? '' : 's'}` : ''} from your net-worth totals. You can undo it; no history is erased.`,
      confirmLabel: 'Remove item',
      cancelLabel: 'Keep item',
      danger: true,
    });
    if (confirmed) deleteMutation.mutate(item);
  };

  if (license && !entitled) {
    return (
      <div className="space-y-5">
        <h1 className="text-white/90 text-[1.6rem] font-light">Net Worth</h1>
        <div className="rounded-[20px] border border-violet-400/15 bg-violet-400/[0.05] p-8 text-center">
          <Scale className="mx-auto text-violet-200/45" size={34} />
          <h2 className="mt-3 text-white/75">Available with GODFIN Max</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-white/35">
            Assets, liabilities, quote history, freshness, and provenance stay
            local. Live quotes use your own Twelve Data key.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-white/90 text-[1.6rem] font-light">Net Worth</h1>
          <p className="text-white/30 text-sm">Local assets, liabilities, freshness, and provenance</p>
        </div>
        <GlassButton
          icon={<Plus size={15} />}
          onClick={() => {
            setEditingId(null);
            setForm(INITIAL_FORM);
            setOpen(true);
          }}
        >
          Add item
        </GlassButton>
      </div>

      {recentDeletion && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-[14px] border border-amber-300/20 bg-amber-300/[0.07] px-4 py-3 text-sm text-amber-50/65">
          <span className="flex-1">Removed {recentDeletion.item.name}. {recentDeletion.affected_records} local record{recentDeletion.affected_records === 1 ? '' : 's'} can be recovered.</span>
          <button
            ref={undoRef}
            type="button"
            onClick={() => restoreMutation.mutate(recentDeletion.id)}
            disabled={restoreMutation.isPending}
            className="min-h-10 rounded-lg border border-amber-200/25 px-3 text-amber-50/80 hover:bg-amber-200/[0.08] disabled:opacity-40"
          >
            {restoreMutation.isPending ? 'Restoring…' : 'Undo'}
          </button>
        </div>
      )}

      <div className="grid sm:grid-cols-3 gap-3">
        {[
          ['Assets', summary?.total_assets, WalletCards, 'text-emerald-200/70'],
          ['Liabilities', summary?.total_liabilities, Landmark, 'text-rose-200/70'],
          ['Net worth', summary?.net_worth, Scale, 'text-cyan-200/75'],
        ].map(([label, value, Icon, tone]) => (
          <div key={label} className="rounded-[18px] border border-white/[0.12] bg-white/[0.06] p-4">
            <Icon size={16} className={`${tone} mb-3`} />
            <div className="text-white/30 text-[0.68rem] uppercase tracking-wider">{label}</div>
            <div className="mt-1 text-white/85 text-xl font-light tabular-nums">
              {money(value, summary?.base_currency)}
            </div>
          </div>
        ))}
      </div>

      {summary?.valuation_status === 'incomplete' && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-[16px] border border-amber-300/20 bg-amber-300/[0.07] p-4"
        >
          <AlertTriangle size={17} className="mt-0.5 shrink-0 text-amber-200/70" />
          <div>
            <div className="text-sm text-amber-100/75">Net-worth totals are temporarily hidden</div>
            <p className="mt-1 text-xs leading-relaxed text-white/40">
              {summary.unavailable_item_count} active item{summary.unavailable_item_count === 1 ? '' : 's'} cannot be valued safely. Review the item message or refresh its quote; GODFIN will not relabel an old value or assume currencies are equal.
            </p>
          </div>
        </div>
      )}

      <div className="rounded-[18px] border border-white/[0.1] bg-white/[0.04] p-4">
        <div className="flex items-center gap-2">
          <KeyRound size={15} className="text-white/35" />
          <h2 className="text-white/65 text-sm">Optional live quotes</h2>
          <CalculationInfo
            title="Live valuation"
            meaning="Liquid holdings use the latest saved unit price and exchange rate."
            formula="quantity × unit price × exchange rate to base currency"
            inputs="Symbol, quantity, quote currency, Twelve Data price, and exchange rate."
            period="Until the displayed quote expiry."
            provenance="Quote and timestamp are saved locally; the API key is encrypted locally."
            caveat="Market data can be delayed or unavailable. Saved manual values remain usable."
          />
        </div>
        <p className="mt-2 text-white/30 text-xs">
          {marketData?.configured
            ? `Twelve Data configured · base currency ${marketData.base_currency}`
            : 'Add your own Twelve Data key. Property, land, gems, and private assets always use sourced manual values.'}
        </p>
        <form
          className="mt-3 flex flex-col sm:flex-row gap-2"
          onSubmit={event => {
            event.preventDefault();
            configMutation.mutate({
              api_key: apiKey || null,
              base_currency: baseCurrency || marketData?.base_currency || 'INR',
            });
          }}
        >
          <input
            type="password"
            aria-label="Twelve Data API key"
            value={apiKey}
            onChange={event => setApiKey(event.target.value)}
            placeholder={marketData?.configured ? 'Replace encrypted API key' : 'Twelve Data API key'}
            className="min-w-0 flex-1 rounded-[12px] border border-white/[0.12] bg-white/[0.05] px-3 py-2 text-sm text-white/70 placeholder:text-white/20 focus:outline-none"
          />
          <label className="sr-only" htmlFor="net-worth-base-currency">Net-worth base currency</label>
          <select
            id="net-worth-base-currency"
            value={baseCurrency || marketData?.base_currency || 'INR'}
            onChange={event => setBaseCurrency(event.target.value)}
            className="w-24 rounded-[12px] border border-white/[0.12] bg-[#102443] px-3 py-2 text-sm text-white/70 focus:outline-none"
          >
            {(marketData?.supported_base_currencies || ['INR', 'USD', 'EUR', 'GBP']).map(currency => (
              <option key={currency} value={currency}>{currency}</option>
            ))}
          </select>
          <GlassButton
            type="submit"
            disabled={configMutation.isPending || (!apiKey.trim() && !baseCurrency)}
          >
            Save market setup
          </GlassButton>
        </form>
      </div>

      {['assets', 'liabilities'].map(group => (
        <section key={group}>
          <h2 className="mb-3 text-white/35 text-[0.7rem] uppercase tracking-wider">
            {group} ({grouped[group].length})
          </h2>
          {grouped[group].length === 0 ? (
            <div className="rounded-[18px] border border-dashed border-white/[0.1] p-6 text-center text-white/25 text-sm">
              No {group} added yet.
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-3">
              {grouped[group].map(item => {
                const fresh = freshness(item);
                return (
                  <article key={item.id} className="rounded-[18px] border border-white/[0.1] bg-white/[0.055] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-white/75 truncate">{item.name}</div>
                        <div className="mt-1 text-white/25 text-xs">
                          {item.asset_class.replaceAll('_', ' ')} · {item.provenance.replaceAll('_', ' ')}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className={item.available ? 'text-white/85 tabular-nums' : 'text-amber-100/70 text-sm'}>
                          {money(item.value_base, summary?.base_currency)}
                        </div>
                        {item.currency !== summary?.base_currency && item.native_value != null && (
                          <div className="mt-0.5 text-white/25 text-[0.65rem]">
                            Native {money(item.native_value, item.currency)}
                          </div>
                        )}
                        {item.symbol && <div className="text-cyan-200/40 text-xs">{item.symbol}</div>}
                      </div>
                    </div>
                    <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className={`h-full rounded-full ${fresh.tone}`} style={{ width: `${fresh.width}%` }} />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[0.65rem]">
                      <span className={item.stale ? 'text-rose-200/55' : 'text-white/25'}>{fresh.label}</span>
                      <span className="text-white/25 truncate max-w-[45%]">{item.source}</span>
                    </div>
                    {!item.available && (
                      <p className="mt-3 rounded-[10px] border border-amber-300/15 bg-amber-300/[0.05] px-3 py-2 text-[0.7rem] leading-relaxed text-amber-100/60">
                        {item.unavailable_reason}
                      </p>
                    )}
                    <div className="mt-3 flex gap-2">
                      {item.valuation_mode === 'market' && (
                        <button
                          onClick={() => quoteMutation.mutate(item.id)}
                          disabled={!marketData?.configured || quoteMutation.isPending}
                          className="inline-flex items-center gap-1.5 text-cyan-200/55 disabled:opacity-30 text-xs"
                        >
                          <RefreshCw size={12} /> Refresh quote
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setEditingId(item.id);
                          setForm({
                            name: item.name,
                            item_type: item.item_type,
                            asset_class: item.asset_class,
                            valuation_mode: item.valuation_mode,
                            symbol: item.symbol || '',
                            quantity: String(item.quantity),
                            currency: item.currency,
                            manual_value: item.manual_value == null ? '' : String(item.manual_value),
                            valuation_source: item.valuation_source || '',
                            source_url: item.source_url || '',
                            valued_at: item.valued_at || '',
                            expires_on: item.expires_on || '',
                            notes: item.notes || '',
                          });
                          setOpen(true);
                        }}
                        className="inline-flex items-center gap-1.5 text-white/35 hover:text-white/65 text-xs"
                      >
                        <Pencil size={12} /> Edit
                      </button>
                      <button
                        onClick={() => requestDelete(item)}
                        disabled={deleteMutation.isPending}
                        className="ml-auto inline-flex items-center gap-1.5 text-rose-200/40 text-xs"
                      >
                        <Trash2 size={12} /> Remove
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ))}

      <p className="text-white/22 text-xs leading-relaxed">
        {summary?.provenance} GODFIN does not treat market quotes or manual
        estimates as audited values.
      </p>

      <AnimatePresence>
        {open && (
          <div
            className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4 backdrop-blur-sm"
            onClick={() => {
              setOpen(false);
              setEditingId(null);
              setForm(INITIAL_FORM);
            }}
          >
            <DialogSurface
              as={motion.form}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              onClick={event => event.stopPropagation()}
              onSubmit={event => {
                event.preventDefault();
                saveMutation.mutate({
                  ...form,
                  quantity: Number(form.quantity),
                  manual_value: form.valuation_mode === 'manual' ? Number(form.manual_value) : null,
                  symbol: form.symbol || null,
                  source_url: form.source_url || null,
                  valued_at: form.valued_at || null,
                  expires_on: form.expires_on || null,
                });
              }}
              labelledBy="net-worth-item-title"
              onClose={() => {
                setOpen(false);
                setEditingId(null);
                setForm(INITIAL_FORM);
              }}
              className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-[22px] border border-white/[0.14] bg-[#102443]/95 p-5 shadow-2xl"
            >
              <div className="mb-5 flex items-center justify-between">
                <h2 id="net-worth-item-title" className="text-white/85">{editingId ? 'Edit valuation' : 'Add asset or liability'}</h2>
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    setEditingId(null);
                    setForm(INITIAL_FORM);
                  }}
                  className="text-white/35"
                  aria-label="Close asset or liability dialog"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                <GlassInput label="Name" value={form.name} required onChange={e => setForm({ ...form, name: e.target.value })} />
                <div>
                  <label htmlFor="net-worth-item-type" className="block text-white/40 text-[0.75rem] mb-1.5">Type</label>
                  <GlassSelect id="net-worth-item-type" value={form.item_type} onChange={value => setForm({ ...form, item_type: value })} options={[
                    { value: 'asset', label: 'Asset' }, { value: 'liability', label: 'Liability' },
                  ]} />
                </div>
                <div>
                  <label htmlFor="net-worth-asset-class" className="block text-white/40 text-[0.75rem] mb-1.5">Class</label>
                  <GlassSelect id="net-worth-asset-class" value={form.asset_class} onChange={value => setForm({ ...form, asset_class: value })} options={ASSET_CLASSES.map(value => ({ value, label: value.replaceAll('_', ' ') }))} />
                </div>
                <div>
                  <label htmlFor="net-worth-valuation-mode" className="block text-white/40 text-[0.75rem] mb-1.5">Valuation</label>
                  <GlassSelect id="net-worth-valuation-mode" value={form.valuation_mode} onChange={value => setForm({ ...form, valuation_mode: value })} options={[
                    { value: 'manual', label: 'Manual sourced value' }, { value: 'market', label: 'Live liquid-asset quote' },
                  ]} />
                </div>
                {form.valuation_mode === 'market' ? (
                  <>
                    <GlassInput label="Twelve Data symbol" value={form.symbol} required placeholder="AAPL or BTC/USD" onChange={e => setForm({ ...form, symbol: e.target.value })} />
                    <GlassInput label="Quantity" type="number" min="0.000001" step="any" value={form.quantity} required onChange={e => setForm({ ...form, quantity: e.target.value })} />
                  </>
                ) : (
                  <GlassInput label="Current value" type="number" min="0" step="any" value={form.manual_value} required onChange={e => setForm({ ...form, manual_value: e.target.value })} />
                )}
                <GlassInput label="Currency" value={form.currency} minLength={3} maxLength={3} required onChange={e => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
                <GlassInput label="Valuation source" value={form.valuation_source} placeholder="Appraisal or statement" onChange={e => setForm({ ...form, valuation_source: e.target.value })} />
                <GlassInput label="Source URL (optional)" type="url" value={form.source_url} onChange={e => setForm({ ...form, source_url: e.target.value })} />
                <GlassInput label="Valued on" type="date" value={form.valued_at} onChange={e => setForm({ ...form, valued_at: e.target.value })} />
                <GlassInput label="Review/expiry date" type="date" value={form.expires_on} onChange={e => setForm({ ...form, expires_on: e.target.value })} />
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <GlassButton
                  variant="ghost"
                  onClick={() => {
                    setOpen(false);
                    setEditingId(null);
                    setForm(INITIAL_FORM);
                  }}
                >
                  Cancel
                </GlassButton>
                <GlassButton type="submit" disabled={saveMutation.isPending}>Save locally</GlassButton>
              </div>
            </DialogSurface>
          </div>
        )}
      </AnimatePresence>
      <ConfirmDialogComponent />
    </div>
  );
}
