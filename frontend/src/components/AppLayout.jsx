import { useState } from 'react';
import { NavLink } from '../router';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  ArrowLeftRight,
  Upload,
  AlertCircle,
  Target,
  DollarSign,
  CreditCard,
  FileText,
  Shield,
  Bot,
  Settings,
  Menu,
  X,
  LogOut,
  KeyRound,
  CalendarDays,
  ScanSearch,
  MoreHorizontal,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import ChangePinModal from './ChangePinModal';
import { GlassBackground } from './GlassBackground';
import { fetchReviewStats, fetchSyncStatus } from '../api/client';

const NAV_GROUPS = [
  {
    label: 'Daily',
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/transactions', icon: ArrowLeftRight, label: 'Transactions' },
      { to: '/transfers', icon: ScanSearch, label: 'Transfers' },
      { to: '/review', icon: AlertCircle, label: 'Review' },
      { to: '/upload', icon: Upload, label: 'Upload' },
    ],
  },
  {
    label: 'Plan',
    items: [
      { to: '/budget', icon: Target, label: 'Budget' },
      { to: '/subscriptions', icon: CreditCard, label: 'Subscriptions' },
      { to: '/income', icon: DollarSign, label: 'Income' },
    ],
  },
  {
    label: 'Insights',
    items: [
      { to: '/reports', icon: FileText, label: 'Reports' },
      { to: '/cash-flow', icon: CalendarDays, label: 'Cash Flow' },
      { to: '/advisor', icon: Bot, label: 'Advisor' },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/audit', icon: Shield, label: 'Audit' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

function ReviewBadge() {
  const { data: stats } = useQuery({
    queryKey: ['reviewStats'],
    queryFn: fetchReviewStats,
    refetchInterval: 30000,
  });

  if (!stats?.queue_size) return null;
  return (
    <span className="absolute -top-1 -right-1 w-4 h-4 bg-amber-500 rounded-full text-[10px] font-medium flex items-center justify-center text-white">
      {stats.queue_size > 9 ? '9+' : stats.queue_size}
    </span>
  );
}

function SyncBanner() {
  const { data: syncStatus } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: fetchSyncStatus,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running') return 3000;
      return false;
    },
    staleTime: 2000,
  });

  if (syncStatus?.status !== 'running') return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[60] h-1">
      <motion.div
        className="h-full bg-gradient-to-r from-amber-500 via-amber-400 to-amber-500"
        initial={{ width: 0 }}
        animate={{ width: `${syncStatus.percent || 0}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  );
}

function SidebarContent({ onItemClick }) {
  const { logout } = useAuth();
  const [changePinOpen, setChangePinOpen] = useState(false);

  return (
    <>
      {/* Logo */}
      <div className="px-5 py-6 mb-2">
        <h1 className="text-white/90 text-[1.3rem] tracking-[-0.04em]" style={{ fontWeight: 300 }}>
          GODFIN
        </h1>
        <p className="text-white/25 text-[0.65rem] tracking-[0.15em] uppercase mt-0.5">
          Personal Finance
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 space-y-3 overflow-y-auto pb-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-3.5 mb-1 text-white/20 text-[0.58rem] uppercase tracking-[0.16em]">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  onClick={onItemClick}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-2 rounded-[14px] transition-all duration-200 text-[0.8rem] group relative ${
                      isActive
                        ? 'bg-white/[0.12] text-white shadow-[0_2px_12px_rgba(100,180,255,0.1),inset_0_1px_0_rgba(255,255,255,0.15)] border border-white/[0.12]'
                        : 'text-white/40 hover:bg-white/[0.06] hover:text-white/70 border border-transparent'
                    }`
                  }
                  style={{ fontWeight: 400 }}
                >
                  <div className="relative">
                    <item.icon size={16} className="shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" />
                    {item.to === '/review' && <ReviewBadge />}
                  </div>
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom Actions */}
      <div className="px-5 py-4 border-t border-white/[0.06]">
        <div className="flex items-center gap-2 mb-3">
          <button
            onClick={() => setChangePinOpen(true)}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-[10px] text-white/40 hover:text-white/70 hover:bg-white/[0.06] transition-all text-[0.75rem]"
          >
            <KeyRound size={14} />
            Change PIN
          </button>
          <button
            onClick={logout}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-[10px] text-white/40 hover:text-rose-400/70 hover:bg-rose-500/[0.06] transition-all text-[0.75rem]"
          >
            <LogOut size={14} />
            Lock
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-400/30 to-violet-400/30 border border-white/[0.15] flex items-center justify-center">
            <span className="text-white/70 text-[0.7rem]" style={{ fontWeight: 500 }}>GF</span>
          </div>
          <div>
            <p className="text-white/60 text-[0.75rem]" style={{ fontWeight: 400 }}>User</p>
            <p className="text-white/25 text-[0.65rem]">v2.0</p>
          </div>
        </div>
      </div>

      <ChangePinModal open={changePinOpen} onClose={() => setChangePinOpen(false)} />
    </>
  );
}

export default function AppLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen w-full" style={{ fontFamily: "'Inter', sans-serif" }}>
      <SyncBanner />
      <GlassBackground />

      <div className="relative z-10 flex min-h-screen">
        {/* Desktop Sidebar */}
        <aside className="hidden lg:flex flex-col w-[220px] shrink-0 sticky top-0 h-screen bg-white/[0.04] backdrop-blur-[32px] border-r border-white/[0.08]">
          <SidebarContent />
        </aside>

        {/* Mobile Header */}
        <div className="lg:hidden fixed top-0 left-0 right-0 z-30 flex items-center justify-between px-4 py-3 bg-white/[0.04] backdrop-blur-[32px] border-b border-white/[0.08]">
          <h1 className="text-white/90 text-[1.1rem] tracking-[-0.04em]" style={{ fontWeight: 300 }}>
            GODFIN
          </h1>
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-[12px] bg-white/[0.08] border border-white/[0.12] text-white/60"
          >
            <Menu size={18} />
          </button>
        </div>

        {/* Mobile Drawer */}
        <AnimatePresence>
          {mobileOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
                onClick={() => setMobileOpen(false)}
              />
              <motion.aside
                initial={{ x: -280 }}
                animate={{ x: 0 }}
                exit={{ x: -280 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                className="fixed top-0 left-0 bottom-0 z-50 w-[260px] flex flex-col bg-[#0d2040]/95 backdrop-blur-[32px] border-r border-white/[0.08] lg:hidden"
              >
                <button
                  onClick={() => setMobileOpen(false)}
                  className="absolute top-4 right-4 p-1.5 rounded-full text-white/40 hover:text-white/70"
                >
                  <X size={18} />
                </button>
                <SidebarContent onItemClick={() => setMobileOpen(false)} />
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        {/* Main Content */}
        <main className="flex-1 min-w-0 pt-16 lg:pt-0">
          <div className="p-4 pb-24 sm:p-6 sm:pb-6 lg:p-8 max-w-[1100px]">
            {children}
          </div>
        </main>
      </div>

      <nav
        className="sm:hidden fixed bottom-0 left-0 right-0 z-30 grid grid-cols-5 bg-[#0b1d39]/95 backdrop-blur-[28px] border-t border-white/[0.1] px-1 pb-[max(0.4rem,env(safe-area-inset-bottom))]"
        aria-label="Primary navigation"
      >
        {[
          { to: '/', icon: LayoutDashboard, label: 'Home' },
          { to: '/transactions', icon: ArrowLeftRight, label: 'Activity' },
          { to: '/review', icon: AlertCircle, label: 'Review' },
          { to: '/cash-flow', icon: CalendarDays, label: 'Cash flow' },
        ].map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `relative min-h-[56px] flex flex-col items-center justify-center gap-1 text-[0.6rem] ${
              isActive ? 'text-cyan-200/80' : 'text-white/35'
            }`}
          >
            <div className="relative">
              <item.icon size={18} />
              {item.to === '/review' && <ReviewBadge />}
            </div>
            {item.label}
          </NavLink>
        ))}
        <button
          onClick={() => setMobileOpen(true)}
          className="min-h-[56px] flex flex-col items-center justify-center gap-1 text-[0.6rem] text-white/35"
        >
          <MoreHorizontal size={18} />
          More
        </button>
      </nav>
    </div>
  );
}
