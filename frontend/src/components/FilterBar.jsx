import { useState, useRef, useEffect } from 'react';
import { Search, X, ArrowUpDown } from 'lucide-react';
import { useTaxonomy } from '../hooks/useTaxonomy';

const SORT_OPTIONS = [
  { label: 'Newest First', sort_by: 'date', sort_order: 'desc' },
  { label: 'Oldest First', sort_by: 'date', sort_order: 'asc' },
  { label: 'Highest to Lowest', sort_by: 'amount', sort_order: 'desc' },
  { label: 'Lowest to Highest', sort_by: 'amount', sort_order: 'asc' },
];

export default function FilterBar({ filters, onChange }) {
  const [sortOpen, setSortOpen] = useState(false);
  const [searchInput, setSearchInput] = useState(filters.search || '');
  const sortRef = useRef(null);
  const debounceRef = useRef(null);
  const { categories, categoryNames } = useTaxonomy();

  // Debounce search input (300ms)
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      if (searchInput !== filters.search) {
        onChange({ ...filters, search: searchInput });
      }
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [searchInput, filters, onChange]);

  useEffect(() => {
    function handleClick(e) {
      if (sortRef.current && !sortRef.current.contains(e.target)) {
        setSortOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  function set(key, value) {
    let next = { ...filters, [key]: value };

    if (key === 'category') next.subcategory = '';

    // Date range validation: ensure date_to >= date_from
    if (key === 'date_from' && value && filters.date_to && value > filters.date_to) {
      next.date_to = value;
    }
    if (key === 'date_to' && value && filters.date_from && value < filters.date_from) {
      next.date_from = value;
    }

    onChange(next);
  }

  function setSort(sort_by, sort_order) {
    onChange({ ...filters, sort_by, sort_order });
    setSortOpen(false);
  }

  function clear() {
    setSearchInput('');
    onChange({
      search: '', category: '', subcategory: '',
      date_from: '', date_to: '',
      sort_by: 'date', sort_order: 'desc',
    });
  }

  const subcategories = filters.category ? categories[filters.category] || [] : [];
  const hasFilters = filters.search || filters.category || filters.subcategory || filters.date_from || filters.date_to;
  const currentSort = SORT_OPTIONS.find(
    (o) => o.sort_by === (filters.sort_by || 'date') && o.sort_order === (filters.sort_order || 'desc')
  );
  const isCustomSort = filters.sort_by && !(filters.sort_by === 'date' && filters.sort_order === 'desc');

  return (
    <div className="flex flex-wrap items-center gap-3 mb-4">
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" aria-hidden="true" />
        <input
          type="text"
          placeholder="Search merchants..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Search by merchant name"
          className="w-full pl-9 pr-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:border-slate-500 focus:outline-none"
        />
      </div>

      <select
        value={filters.category || ''}
        onChange={(e) => set('category', e.target.value)}
        aria-label="Filter by category"
        className="bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:border-slate-500 focus:outline-none"
      >
        <option value="">All Categories</option>
        {categoryNames.map((cat) => (
          <option key={cat} value={cat}>{cat}</option>
        ))}
      </select>

      {subcategories.length > 0 && (
        <select
          value={filters.subcategory || ''}
          onChange={(e) => set('subcategory', e.target.value)}
          aria-label="Filter by subcategory"
          className="bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:border-slate-500 focus:outline-none"
        >
          <option value="">All Subcategories</option>
          {subcategories.map((sub) => (
            <option key={sub} value={sub}>{sub}</option>
          ))}
        </select>
      )}

      <input
        type="date"
        value={filters.date_from || ''}
        onChange={(e) => set('date_from', e.target.value)}
        aria-label="Filter from date"
        className="bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:border-slate-500 focus:outline-none"
      />

      <input
        type="date"
        value={filters.date_to || ''}
        onChange={(e) => set('date_to', e.target.value)}
        aria-label="Filter to date"
        className="bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:border-slate-500 focus:outline-none"
      />

      {/* Sort dropdown */}
      <div className="relative" ref={sortRef}>
        <button
          onClick={() => setSortOpen(!sortOpen)}
          aria-expanded={sortOpen}
          aria-haspopup="listbox"
          aria-label="Sort options"
          className={`flex items-center gap-1.5 px-3 py-2 border rounded-lg text-sm transition-colors ${
            isCustomSort
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white'
          }`}
          title={currentSort?.label || 'Sort'}
        >
          <ArrowUpDown className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline text-xs">{currentSort?.label || 'Sort'}</span>
        </button>

        {sortOpen && (
          <div className="absolute right-0 top-full mt-1 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-20 overflow-hidden">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={`${opt.sort_by}-${opt.sort_order}`}
                onClick={() => setSort(opt.sort_by, opt.sort_order)}
                className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                  filters.sort_by === opt.sort_by && filters.sort_order === opt.sort_order
                    ? 'text-emerald-400 bg-emerald-500/10'
                    : 'text-slate-300 hover:bg-slate-700/50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {hasFilters && (
        <button
          onClick={clear}
          className="text-slate-400 hover:text-white transition-colors p-2"
          title="Clear filters"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
