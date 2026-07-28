import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate, RouterProvider, useLocation } from './router';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuditProvider } from './context/AuditContext';
import AppLayout from './components/AppLayout';
import GlobalErrorToasts from './components/GlobalErrorToasts';
import PinScreen from './pages/PinScreen';
import { fetchOnboardingStatus } from './api/client';

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
};

function AppRoutes() {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  const { data: onboarding, isLoading: onboardingLoading } = useQuery({
    queryKey: ['onboarding'],
    queryFn: fetchOnboardingStatus,
    enabled: isAuthenticated,
  });
  if (pathname === '/pin') return <PinRoute />;
  if (pathname === '/onboarding') {
    return (
      <ProtectedRoute>
        <Suspense fallback={<p className="p-8 text-sm text-white/40">Loading…</p>}>
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
    && !onboardingTaskRoutes.has(pathname)
  ) {
    return <Navigate to="/onboarding" replace />;
  }
  const Page = ROUTES[pathname];
  if (!Page) return <Navigate to="/" replace />;
  return (
    <ProtectedRoute>
      <AppLayout>
        <Suspense fallback={<p className="p-8 text-sm text-white/40">Loading…</p>}>
          <Page />
        </Suspense>
      </AppLayout>
    </ProtectedRoute>
  );
}
