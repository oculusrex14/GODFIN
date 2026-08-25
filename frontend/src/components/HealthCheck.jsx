import { useQuery } from '@tanstack/react-query';
import { fetchHealth, isBackendAlive } from '../api/client';
import { Activity } from 'lucide-react';

export default function HealthCheck() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30000,
  });

  return (
    <div className="flex items-center gap-3 rounded-xl bg-slate-800/50 border border-slate-700 px-5 py-4 backdrop-blur-md">
      <Activity className="h-5 w-5 text-ink-muted" />
      <div>
        <p className="text-sm text-ink-muted">System Status</p>
        {isLoading ? (
          <p className="text-sm text-ink-muted">Checking...</p>
        ) : isError ? (
          <p className="text-sm font-medium text-rose-200">Backend Offline</p>
        ) : (
          <p className="text-sm font-medium text-emerald-200">
            {isBackendAlive(data) ? 'Connected' : 'Error'} &middot; v{data.version}
          </p>
        )}
      </div>
    </div>
  );
}
