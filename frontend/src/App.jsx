import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MotionConfig } from 'framer-motion';
import { Navigate, RouterProvider, useLocation } from './router';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuditProvider } from './context/AuditContext';
import AppLayout from './components/AppLayout';
import LockedFeaturePage from './components/LockedFeaturePage';
import GlobalErrorToasts from './components/GlobalErrorToasts';
import PinScreen from './pages/PinScreen';
import { fetchLicenseNavigation, fetchOnboardingStatus } from './api/client';
import { lockedRouteMetadata } from './lib/tierNavigation';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Transactions = lazy(() => import('./pages/Transactions'));
const ReviewQueue = lazy(() => import('./pages/ReviewQueue'));
const UploadPage = lazy(() => import('./pages/Upload'));
const Budget = lazy(() => import('./pages/Budget'));
const Subscriptions = lazy(() => import('./pages/Subscriptions'));
const Income = lazy(() => import('./pages/Income'));
const Reports = lazy(() => import('./pages/Reports'));
const AuditManager = lazy(() => import('./pages/AuditManager'));
const Advisor = lazy(() => import('./pages/Advisor'));
const Settings = lazy(() => import('./pages/Settings'));
const CashFlow = lazy(() => import('./pages/CashFlow'));
const Transfers = lazy(() => import('./pages/Transfers'));
const Onboarding = lazy(() => import('./pages/Onboarding'));
const LearnGodfin = lazy(() => import('./pages/LearnGodfin'));
const NetWorth = lazy(() => import('./pages/NetWorth'));
const BehaviorInsights = lazy(() => import('./pages/BehaviorInsights'));

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return null;
  if (!isAuthenticated) return <Navigate to="/pin" replace />;
  return children;
}

function PinRoute() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return null;
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <PinScreen />;
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <RouterProvider>
        <AuthProvider>
          <ThemeProvider>
            <ToastProvider>
              <GlobalErrorToasts />
              <AuditProvider>
                <AppRoutes />
              </AuditProvider>
            </ToastProvider>
          </ThemeProvider>
        </AuthProvider>
      </RouterProvider>
    </MotionConfig>
  );
}

const ROUTES = {
  '/': Dashboard,
  '/transactions': Transactions,
  '/review': ReviewQueue,
  '/upload': UploadPage,
  '/budget': Budget,
  '/subscriptions': Subscriptions,
  '/income': Income,
  '/reports': Reports,
  '/audit': AuditManager,
  '/advisor': Advisor,
  '/settings': Settings,
  '/cash-flow': CashFlow,
  '/transfers': Transfers,
  '/learn': LearnGodfin,
  '/net-worth': NetWorth,
  '/behavior-insights': BehaviorInsights,
};

function AppRoutes() {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  const { data: onboarding, isLoading: onboardingLoading } = useQuery({
    queryKey: ['onboarding'],
    queryFn: fetchOnboardingStatus,
    enabled: isAuthenticated,
  });
  const {
    data: licenseNavigation,
    isLoading: licenseNavigationLoading,
    isError: licenseNavigationError,
    isFetching: licenseNavigationFetching,
    refetch: refetchLicenseNavigation,
  } = useQuery({
    queryKey: ['licenseNavigation'],
    queryFn: fetchLicenseNavigation,
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
  if (pathname === '/pin') return <PinRoute />;
  if (pathname === '/onboarding') {
    return (
      <ProtectedRoute>
        <Suspense fallback={<p className="p-8 text-sm text-ink-muted">Loading…</p>}>
          <Onboarding />
        </Suspense>
      </ProtectedRoute>
    );
  }
  const onboardingTaskRoutes = new Set(['/upload', '/review', '/settings']);
  if (
    isAuthenticated
    && !onboardingLoading
    && onboarding?.completed === false
    && onboarding?.deferred !== true
    && !onboardingTaskRoutes.has(pathname)
  ) {
    return <Navigate to="/onboarding" replace />;
  }
  const Page = ROUTES[pathname];
  if (!Page) return <Navigate to="/" replace />;
  if (isAuthenticated && licenseNavigationLoading) {
    return (
      <ProtectedRoute>
        <AppLayout>
          <p className="p-8 text-sm text-ink-muted" role="status">
            Checking feature access…
          </p>
        </AppLayout>
      </ProtectedRoute>
    );
  }
  if (isAuthenticated && licenseNavigationError) {
    return (
      <ProtectedRoute>
        <AppLayout>
          <div className="mx-auto max-w-xl p-8 text-center" role="alert">
            <h1 className="text-xl font-semibold text-ink-primary">
              GODFIN could not check feature access
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              Your data is safe. Make sure the local backend is online, then try again.
            </p>
            <button
              type="button"
              className="mt-5 rounded-xl border border-cyan-300/40 bg-cyan-300/10 px-4 py-2 text-sm font-medium text-cyan-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200 disabled:cursor-wait disabled:opacity-60"
              onClick={() => refetchLicenseNavigation()}
              disabled={licenseNavigationFetching}
            >
              {licenseNavigationFetching ? 'Checking…' : 'Try again'}
            </button>
          </div>
        </AppLayout>
      </ProtectedRoute>
    );
  }
  const lockedRule = lockedRouteMetadata(pathname, licenseNavigation);
  return (
    <ProtectedRoute>
      <AppLayout>
        {lockedRule ? (
          <LockedFeaturePage rule={lockedRule} />
        ) : (
          <Suspense fallback={<p className="p-8 text-sm text-ink-muted">Loading…</p>}>
            <Page />
          </Suspense>
        )}
      </AppLayout>
    </ProtectedRoute>
  );
}
