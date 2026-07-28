import { createContext, useContext, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAuditSessions } from '../api/client';
import { useAuth } from './AuthContext';

const AuditContext = createContext({
  activeAudit: null,
  isAuditActive: false,
});

export function AuditProvider({ children }) {
  const { isAuthenticated } = useAuth();

  const { data: sessions, refetch } = useQuery({
    queryKey: ['auditSessions'],
    queryFn: () => fetchAuditSessions({ status: 'draft' }),
    enabled: isAuthenticated,
    refetchInterval: 30000, // Check every 30s
  });

  // Sync audit state across tabs using storage events
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === 'godfin_audit_changed') {
        refetch();
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [refetch]);

  // Notify other tabs when audit state changes
  const notifyOtherTabs = () => {
    localStorage.setItem('godfin_audit_changed', Date.now().toString());
  };

  // Find any draft (active) audit session
  const auditList = Array.isArray(sessions) ? sessions : sessions?.items || [];
  const activeAudit = auditList.find(s => s.status === 'draft') || null;

  return (
    <AuditContext.Provider value={{ activeAudit, isAuditActive: !!activeAudit, notifyOtherTabs }}>
      {children}
    </AuditContext.Provider>
  );
}

export function useAudit() {
  return useContext(AuditContext);
}
