import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { addMonths, format, subMonths } from 'date-fns';
import { motion } from 'framer-motion';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, CalendarDays } from 'lucide-react';

import { fetchCashFlowCalendar } from '../api/client';
import { Link } from '../router';

function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value || 0);
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function CashFlow() {
  const [month, setMonth] = useState(format(new Date(), 'yyyy-MM'));
  const selected = new Date(`${month}-01T12:00:00`);
  const currentMonth = format(new Date(), 'yyyy-MM');
  const { data, isLoading } = useQuery({
    queryKey: ['cashFlowCalendar', month],
    queryFn: () => fetchCashFlowCalendar(month),
  });
  const firstWeekday = (selected.getDay() + 6) % 7;

  return (
    <div>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-center justify-between gap-4 mb-6"
      >
        <div>
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>
            Cash-flow Calendar
          </h1>
          <p className="text-white/30 text-[0.8rem]">Income and spending by day. Transfers are excluded.</p>
        </div>
        <div className="flex items-center gap-2 min-h-11">
          <button
            onClick={() => setMonth(format(subMonths(selected, 1), 'yyyy-MM'))}
            className="min-w-11 min-h-11 grid place-items-center rounded-xl text-white/40 hover:text-white/70 hover:bg-white/[0.06]"
            aria-label="Previous month"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="min-w-32 text-center text-sm text-white/70">{format(selected, 'MMMM yyyy')}</span>
          <button
            onClick={() => setMonth(format(addMonths(selected, 1), 'yyyy-MM'))}
            disabled={month >= currentMonth}
            className="min-w-11 min-h-11 grid place-items-center rounded-xl text-white/40 hover:text-white/70 hover:bg-white/[0.06] disabled:opacity-25"
            aria-label="Next month"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        {[
          { label: 'Income', value: data?.total_income, color: 'text-emerald-300', icon: ArrowUp },
          { label: 'Spending', value: data?.total_spend, color: 'text-rose-300', icon: ArrowDown },
          { label: 'Net cash flow', value: data?.net, color: data?.net >= 0 ? 'text-cyan-300' : 'text-amber-300', icon: CalendarDays },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="rounded-[18px] bg-white/[0.07] border border-white/[0.14] p-4">
            <div className="flex items-center gap-2 text-white/30 text-xs"><Icon size={14} /> {label}</div>
            <div className={`mt-2 text-xl tabular-nums ${color}`}>{isLoading ? '—' : money(value)}</div>
          </div>
        ))}
      </div>

      <div className="rounded-[20px] bg-white/[0.07] border border-white/[0.14] p-3 sm:p-5 overflow-x-auto">
        <div className="grid grid-cols-7 gap-1 sm:gap-2 min-w-[560px]">
          {WEEKDAYS.map(day => (
            <div key={day} className="text-center text-[0.65rem] uppercase tracking-wide text-white/25 py-2">
              {day}
            </div>
          ))}
          {Array.from({ length: firstWeekday }, (_, index) => (
            <div key={`blank-${index}`} />
          ))}
          {(data?.days || []).map(day => {
            const magnitude = Math.max(day.spend, day.income);
            const intensity = data?.max_daily_flow ? Math.min(1, magnitude / data.max_daily_flow) : 0;
            const positive = day.net >= 0;
            const background = magnitude
              ? positive
                ? `rgba(52, 211, 153, ${0.08 + intensity * 0.28})`
                : `rgba(251, 113, 133, ${0.08 + intensity * 0.28})`
              : 'rgba(255,255,255,0.025)';
            return (
              <Link
                key={day.date}
                to={`/transactions?date_from=${day.date}&date_to=${day.date}`}
                className="min-h-[86px] rounded-xl border border-white/[0.07] p-2 hover:border-white/[0.22] transition-colors"
                style={{ background }}
                aria-label={`${day.date}: income ${money(day.income)}, spending ${money(day.spend)}`}
              >
                <div className="text-white/50 text-xs">{Number(day.date.slice(-2))}</div>
                {day.transaction_count > 0 && (
                  <div className="mt-2 space-y-1 text-[0.62rem] tabular-nums">
                    {day.income > 0 && <div className="text-emerald-200/80">+{money(day.income)}</div>}
                    {day.spend > 0 && <div className="text-rose-200/80">−{money(day.spend)}</div>}
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      </div>
      <p className="mt-3 text-white/25 text-xs">Tap a day to open its transactions.</p>
    </div>
  );
}
