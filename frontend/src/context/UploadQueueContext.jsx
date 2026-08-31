import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  importStatement,
  previewStatement,
  reconcileStatement,
} from '../api/client';

const UploadQueueContext = createContext(null);

const PROGRESS_CAPS = {
  parsing: 28,
  reconciling: 58,
  importing: 94,
};

export function UploadQueueProvider({ children }) {
  const [automaticQueue, setAutomaticQueue] = useState([]);
  const [activeAutomaticId, setActiveAutomaticId] = useState(null);
  const [reviewAllFirst, setReviewAllFirst] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const processingRef = useRef(false);
  const queryClient = useQueryClient();

  const updateAutomatic = useCallback((id, patch) => {
    setAutomaticQueue(current => current.map(item => (
      item.id === id ? { ...item, ...patch } : item
    )));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setAutomaticQueue((current) => {
        let changed = false;
        const next = current.map((item) => {
          const cap = PROGRESS_CAPS[item.status];
          const progress = Number(item.progress || 0);
          if (!cap || progress >= cap) return item;
          changed = true;
          return { ...item, progress: Math.min(cap, progress + 2) };
        });
        return changed ? next : current;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, []);

  const runExclusively = useCallback(async (operation) => {
    if (processingRef.current) return false;
    processingRef.current = true;
    setIsProcessing(true);
    try {
      await operation();
      return true;
    } finally {
      processingRef.current = false;
      setIsProcessing(false);
    }
  }, []);

  const reviewAutomatic = useCallback((entry) => runExclusively(async () => {
    updateAutomatic(entry.id, {
      status: 'parsing',
      error: '',
      progress: 8,
      progressLabel: 'Reading and checking the statement',
    });
    try {
      await previewStatement(
        entry.file,
        entry.password || null,
        entry.accountId || null,
      );
      updateAutomatic(entry.id, {
        step: 2,
        status: 'reconciling',
        progress: 32,
        progressLabel: 'Comparing with transactions already in GODFIN',
      });
      const data = await reconcileStatement(
        entry.file,
        entry.accountId || null,
        entry.password || null,
      );
      updateAutomatic(entry.id, {
        step: 2,
        status: 'reviewed',
        progress: 60,
        progressLabel: 'Review complete',
        reconcileData: data,
        accountId: data.account_id || entry.accountId,
        error: '',
      });
    } catch (error) {
      updateAutomatic(entry.id, {
        status: 'failed',
        progress: 0,
        error: error?.message || 'GODFIN could not read and reconcile this statement.',
      });
    }
  }), [runExclusively, updateAutomatic]);

  const importAutomatic = useCallback((entry) => runExclusively(async () => {
    updateAutomatic(entry.id, {
      status: 'importing',
      error: '',
      progress: 68,
      progressLabel: 'Saving transactions and updating balances',
    });
    try {
      const data = await importStatement(entry.file, entry.reconcileData?.account_id, {
        password: entry.password || null,
        importNew: true,
        detectIncome: true,
        confirmReconciled: true,
        acceptedFingerprint: entry.reconcileData?.parse_fingerprint,
      });
      updateAutomatic(entry.id, {
        importResult: data,
        step: 3,
        status: 'complete',
        progress: 100,
        progressLabel: 'Statement finished',
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['transactions'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboardStats'] }),
        queryClient.invalidateQueries({ queryKey: ['reviewStats'] }),
        queryClient.invalidateQueries({ queryKey: ['reviewQueue'] }),
        queryClient.invalidateQueries({ queryKey: ['uploadReviewQueue'] }),
      ]);
    } catch (error) {
      updateAutomatic(entry.id, {
        status: 'reviewed',
        progress: 60,
        error: error?.message || 'No transactions were imported.',
      });
    }
  }), [queryClient, runExclusively, updateAutomatic]);

  const clearAutomaticQueue = useCallback(() => {
    if (processingRef.current) return false;
    setAutomaticQueue([]);
    setActiveAutomaticId(null);
    setReviewAllFirst(true);
    return true;
  }, []);

  const value = useMemo(() => ({
    automaticQueue,
    setAutomaticQueue,
    activeAutomaticId,
    setActiveAutomaticId,
    reviewAllFirst,
    setReviewAllFirst,
    isProcessing,
    updateAutomatic,
    reviewAutomatic,
    importAutomatic,
    clearAutomaticQueue,
  }), [
    activeAutomaticId,
    automaticQueue,
    clearAutomaticQueue,
    importAutomatic,
    isProcessing,
    reviewAllFirst,
    reviewAutomatic,
    updateAutomatic,
  ]);

  return (
    <UploadQueueContext.Provider value={value}>
      {children}
    </UploadQueueContext.Provider>
  );
}

export function useUploadQueue() {
  const context = useContext(UploadQueueContext);
  if (!context) {
    throw new Error('useUploadQueue must be used within UploadQueueProvider');
  }
  return context;
}
