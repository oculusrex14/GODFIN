import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Mail, Loader2, Check, AlertCircle, RefreshCw, Calendar,
  Unlink, ExternalLink, Clock, Database, Info, TrendingUp, CheckCircle, XCircle
} from 'lucide-react';
import {
  fetchGmailStatus,
  fetchGmailAuthUrl,
  submitGmailManualCode,
  disconnectGmail,
  fetchSchedulerStatus,
  startInitialSync,
  fetchSyncStatus,
  startIngestionWithDates,
  fetchIngestionProgress,
  fetchIngestSettings,
  updateIngestSettings,
} from '../../api/client';
import { openExternalUrl } from '../../config/external';

// Detect if we're on localhost or network IP
function isLocalhost() {
  if (window.location.protocol === 'godfin:') return true;
  const hostname = window.location.hostname;
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}

function GmailSettings() {
  const queryClient = useQueryClient();
  const [showOAuthModal, setShowOAuthModal] = useState(false);
  const [showDateRangeModal, setShowDateRangeModal] = useState(false);
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [oauthUrl, setOauthUrl] = useState('');
  const [manualCode, setManualCode] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [clearDataOnDisconnect, setClearDataOnDisconnect] = useState(false);
  const [toast, setToast] = useState(null);
  const [autoIngestEnabled, setAutoIngestEnabled] = useState(true);
  const [ingestFrequency, setIngestFrequency] = useState(15);
  const [ingestJustCompleted, setIngestJustCompleted] = useState(false);
  const [awaitingOAuth, setAwaitingOAuth] = useState(false);

  const getErrorMessage = (err) => {
    if (typeof err === 'string') return err;
    if (err?.message) return err.message;
    if (err?.detail) return err.detail;
    return 'An error occurred';
  };

  const showToast = (msg, type = 'success') => {
    const message = typeof msg === 'object' ? JSON.stringify(msg) : msg;
    setToast({ msg: message, type });
    // Longer duration for success messages so user can see the result
    const duration = type === 'success' ? 6000 : 4000;
    setTimeout(() => setToast(null), duration);
  };

  // Fetch Gmail status
  const { data: gmailStatus } = useQuery({
    queryKey: ['gmailStatus'],
    queryFn: fetchGmailStatus,
    staleTime: 30000,
    refetchInterval: awaitingOAuth ? 2000 : false,
  });

  // Fetch scheduler/history status
  const { data: schedulerStatus } = useQuery({
    queryKey: ['schedulerStatus'],
    queryFn: fetchSchedulerStatus,
    enabled: gmailStatus?.connected,
    staleTime: 60000,
  });

  // Fetch auto-ingestion settings
  const { data: ingestSettings } = useQuery({
    queryKey: ['ingestSettings'],
    queryFn: fetchIngestSettings,
    enabled: gmailStatus?.connected,
    staleTime: 60000,
  });

  // Update settings when data changes
  useEffect(() => {
    if (ingestSettings) {
      setAutoIngestEnabled(ingestSettings.auto_ingestion_enabled !== false);
      setIngestFrequency(ingestSettings.frequency_minutes || 15);
    }
  }, [ingestSettings]);

  // Mutation to update auto-ingestion settings
  const updateIngestSettingsMutation = useMutation({
    mutationFn: ({ enabled, frequency }) => updateIngestSettings(enabled, frequency),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ingestSettings'] });
      showToast('Auto-ingestion settings updated');
    },
    onError: (err) => showToast(getErrorMessage(err), 'error'),
  });

  // Get OAuth URL
  const authUrlMutation = useMutation({
    mutationFn: async () => {
      // Use out-of-band flow for network access (can't use private IPs in Google OAuth)
      const useOob = !isLocalhost();
      console.log('Fetching Gmail auth URL, useOob:', useOob, 'isLocalhost:', isLocalhost());
      const data = await fetchGmailAuthUrl(useOob);
      console.log('Got auth response:', data);

      if (!data.auth_url) {
        throw new Error('No auth URL returned from server');
      }

      if (useOob || data.flow === 'manual') {
        // Show auth URL for manual code entry
        setOauthUrl(data.auth_url);
        setShowOAuthModal(true);
      } else {
        setOauthUrl(data.auth_url);
        setShowOAuthModal(true);
        setAwaitingOAuth(true);
        openExternalUrl(data.auth_url);
        showToast('Complete the Google approval in your browser, then return to GODFIN.', 'info');
      }
    },
    onError: (err) => {
      console.error('Gmail auth error:', err);
      showToast(getErrorMessage(err), 'error');
    },
  });

  useEffect(() => {
    if (!awaitingOAuth || !gmailStatus?.connected) return;
    setAwaitingOAuth(false);
    setShowOAuthModal(false);
    setOauthUrl('');
    showToast('Gmail connected successfully!');
  }, [awaitingOAuth, gmailStatus?.connected]);

  // Manual OAuth code submission
  const manualCodeMutation = useMutation({
    mutationFn: submitGmailManualCode,
    onSuccess: () => {
      setShowOAuthModal(false);
      setManualCode('');
      queryClient.invalidateQueries({ queryKey: ['gmailStatus'] });
      showToast('Gmail connected successfully!');
    },
    onError: (err) => showToast(getErrorMessage(err), 'error'),
  });

  // Background initial sync mutation — kicks off and returns immediately
  const initialSyncMutation = useMutation({
    mutationFn: startInitialSync,
    onSuccess: (data) => {
      if (data.already_completed) {
        showToast(data.message, 'info');
      } else if (data.already_running) {
        showToast('Sync already in progress', 'info');
      } else {
        showToast('Initial sync started in background');
      }
    },
    onError: (err) => showToast(getErrorMessage(err), 'error'),
  });

  // Poll sync status while running
  const { data: syncStatus } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: fetchSyncStatus,
    enabled: !!gmailStatus?.connected,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running') return 3000;
      return false;
    },
    staleTime: 2000,
  });

  // When sync completes, invalidate related queries
  useEffect(() => {
    if (syncStatus?.status === 'completed') {
      queryClient.invalidateQueries({ queryKey: ['gmailStatus'] });
      queryClient.invalidateQueries({ queryKey: ['schedulerStatus'] });
    }
  }, [syncStatus?.status, queryClient]);

  // Date range ingestion mutation — kicks off background ingestion
  const dateRangeMutation = useMutation({
    mutationFn: startIngestionWithDates,
    onSuccess: (data) => {
      if (data.already_running) {
        showToast('Ingestion already in progress', 'info');
      } else {
        showToast('Ingestion started in background');
      }
      // Don't close modal — show progress instead
    },
    onError: (err) => showToast(getErrorMessage(err), 'error'),
  });

  // Poll ingestion progress
  const { data: ingestProgress } = useQuery({
    queryKey: ['ingestProgress'],
    queryFn: fetchIngestionProgress,
    enabled: !!gmailStatus?.connected,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running') return 2000;
      return false;
    },
    staleTime: 1000,
  });

  // Track previous ingest status for transition detection
  const prevIngestStatusRef = useRef(null);

  // Handle completed transition
  useEffect(() => {
    const prev = prevIngestStatusRef.current;
    const curr = ingestProgress?.status;
    if (prev === 'running' && curr === 'completed') {
      setIngestJustCompleted(true);
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['schedulerStatus'] });
      queryClient.invalidateQueries({ queryKey: ['gmailStatus'] });
      const r = ingestProgress?.result;
      if (r) {
        showToast(`Ingestion complete: ${r.created ?? 0} created, ${r.processed ?? 0} processed`, 'success');
      } else {
        showToast('Ingestion complete', 'success');
      }
      // Auto-close modal and reset after showing results
      setTimeout(() => {
        setShowDateRangeModal(false);
        setStartDate('');
        setEndDate('');
        setIngestJustCompleted(false);
      }, 5000);
    }
    prevIngestStatusRef.current = curr;
  }, [ingestProgress?.status, ingestProgress?.result, queryClient]);

  // Disconnect mutation
  const disconnectMutation = useMutation({
    mutationFn: () => disconnectGmail(clearDataOnDisconnect),
    onSuccess: (data) => {
      setShowDisconnectModal(false);
      setClearDataOnDisconnect(false);
      queryClient.invalidateQueries({ queryKey: ['gmailStatus'] });
      queryClient.invalidateQueries({ queryKey: ['schedulerStatus'] });
      queryClient.invalidateQueries({ queryKey: ['ingestSettings'] });
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      showToast(data.message);
    },
    onError: (err) => showToast(getErrorMessage(err), 'error'),
  });

  const handleConnect = () => {
    authUrlMutation.mutate();
  };

  const handleManualCodeSubmit = () => {
    if (!manualCode.trim()) return;
    manualCodeMutation.mutate(manualCode.trim());
  };

  const handleInitialSync = () => {
    initialSyncMutation.mutate();
  };

  const handleIngestNow = () => {
    // Default to last 7 days if no dates set
    if (!startDate || !endDate) {
      const today = new Date();
      const lastWeek = new Date(today);
      lastWeek.setDate(lastWeek.getDate() - 7);
      setEndDate(today.toISOString().split('T')[0]);
      setStartDate(lastWeek.toISOString().split('T')[0]);
    }
    setShowDateRangeModal(true);
  };

  const handleDateRangeSubmit = () => {
    if (!startDate || !endDate) {
      showToast('Please select both start and end dates', 'error');
      return;
    }
    // Close modal immediately, ingestion runs in background
    setShowDateRangeModal(false);
    dateRangeMutation.mutate({ startDate, endDate });
  };

  const handleDisconnect = () => {
    disconnectMutation.mutate();
  };

  // Check URL params for OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const gmailConnected = params.get('gmail') === 'connected' || params.get('gmail_connected') === 'true';
    const gmailError = params.get('gmail_error');

    if (gmailConnected) {
      queryClient.invalidateQueries({ queryKey: ['gmailStatus'] });
      showToast('Gmail connected successfully!');
      // Clear the query param
      window.history.replaceState({}, '', window.location.pathname);
    } else if (gmailError) {
      showToast(`Gmail connection failed: ${gmailError}`, 'error');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [queryClient]);

  const isConnected = gmailStatus?.connected;
  const history = schedulerStatus?.history;

  // Format date for display
  const formatDate = (isoString) => {
    if (!isoString) return 'Never';
    const date = new Date(isoString);
    return date.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-4">
      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className={`px-4 py-2 rounded-lg text-sm ${
              toast.type === 'error'
                ? 'bg-red-500/10 border border-red-500/30 text-red-400'
                : toast.type === 'info'
                ? 'bg-blue-500/10 border border-blue-500/30 text-blue-400'
                : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
            }`}
          >
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Connection Status Card */}
      <div className="bg-slate-800/40 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isConnected ? 'bg-emerald-500/20' : 'bg-slate-700/50'}`}>
              <Mail className={`h-5 w-5 ${isConnected ? 'text-emerald-400' : 'text-slate-400'}`} />
            </div>
            <div>
              <div className="text-white font-medium">
                {isConnected ? 'Gmail Connected' : 'Gmail Not Connected'}
              </div>
              <div className="text-slate-500 text-xs">
                {isConnected
                  ? 'Ready to ingest HDFC Bank transaction emails'
                  : 'Connect your Gmail to automatically import transactions'}
              </div>
            </div>
          </div>

          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={authUrlMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors disabled:opacity-50 text-sm"
            >
              {authUrlMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="h-4 w-4" />
              )}
              Connect Gmail
            </button>
          ) : (
            <button
              onClick={() => setShowDisconnectModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20 transition-colors text-sm"
            >
              <Unlink className="h-4 w-4" />
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* Connected State - Sync Controls */}
      {isConnected && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="space-y-4"
        >
          {/* Initial Sync Section */}
          <div className="bg-slate-800/40 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10">
                  <Database className="h-5 w-5 text-amber-400" />
                </div>
                <div>
                  <div className="text-white font-medium">Initial Sync</div>
                  <div className="text-slate-500 text-xs">
                    Import all transactions from start of year
                  </div>
                </div>
              </div>

              <button
                onClick={handleInitialSync}
                disabled={initialSyncMutation.isPending || syncStatus?.status === 'running'}
                className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 text-amber-400 rounded-lg hover:bg-amber-500/20 transition-colors disabled:opacity-50 text-sm"
              >
                {initialSyncMutation.isPending || syncStatus?.status === 'running' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {syncStatus?.status === 'running' ? 'Syncing...' : 'Initial Sync'}
              </button>
            </div>

            {/* Progress bar during sync */}
            {syncStatus?.status === 'running' && (
              <div className="mt-3 pt-3 border-t border-slate-700/30">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <span>Processing emails...</span>
                  <span>{syncStatus.processed} / {syncStatus.total || '?'} ({syncStatus.percent}%)</span>
                </div>
                <div className="w-full h-2 bg-slate-700/50 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${syncStatus.percent}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  />
                </div>
              </div>
            )}

            {/* Sync completed message with details */}
            {syncStatus?.status === 'completed' && !history?.initial_sync_date_range && (
              <div className="mt-3 pt-3 border-t border-slate-700/30">
                <div className="flex items-center gap-2 text-xs text-emerald-400 mb-2">
                  <Check className="h-3 w-3" />
                  <span>Sync complete!</span>
                </div>
                {syncStatus.result && (() => {
                  try {
                    const r = typeof syncStatus.result === 'string' ? JSON.parse(syncStatus.result.replace(/'/g, '"')) : syncStatus.result;
                    return (
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400 bg-slate-800/30 rounded-lg p-2.5">
                        <span>Processed:</span><span className="text-white/70">{r.processed ?? '—'}</span>
                        <span>Created:</span><span className="text-emerald-400">{r.created ?? '—'}</span>
                        <span>Duplicates skipped:</span><span>{r.skipped_duplicate ?? '—'}</span>
                        <span>No pattern match:</span><span>{r.skipped_no_match ?? '—'}</span>
                        <span>Blacklisted:</span><span>{r.skipped_blacklist ?? '—'}</span>
                        {r.errors > 0 && <><span className="text-red-400">Errors:</span><span className="text-red-400">{r.errors}</span></>}
                      </div>
                    );
                  } catch { return null; }
                })()}
              </div>
            )}

            {/* Sync error */}
            {syncStatus?.status === 'error' && (
              <div className="mt-3 pt-3 border-t border-slate-700/30 flex items-center gap-2 text-xs text-red-400">
                <AlertCircle className="h-3 w-3" />
                <span>Sync failed: {syncStatus.error}</span>
              </div>
            )}

            {/* Initial sync date range display */}
            {history?.initial_sync_date_range && (
              <div className="mt-3 pt-3 border-t border-slate-700/30 flex items-center gap-2 text-xs text-slate-400">
                <Check className="h-3 w-3 text-emerald-400" />
                <span>Completed:</span>
                <span className="text-slate-300">{history.initial_sync_date_range}</span>
              </div>
            )}
          </div>

          {/* Ingest Now Section */}
          <div className="bg-slate-800/40 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg transition-colors ${
                  ingestProgress?.status === 'running' ? 'bg-blue-500/20 animate-pulse' :
                  ingestJustCompleted ? 'bg-emerald-500/20' : 'bg-blue-500/10'
                }`}>
                  {ingestProgress?.status === 'running' ? (
                    <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />
                  ) : ingestJustCompleted ? (
                    <Check className="h-5 w-5 text-emerald-400" />
                  ) : (
                    <Calendar className="h-5 w-5 text-blue-400" />
                  )}
                </div>
                <div>
                  <div className="text-white font-medium">Ingest Now</div>
                  <div className="text-slate-500 text-xs">
                    {ingestProgress?.status === 'running' ? 'Syncing transactions...' :
                     ingestJustCompleted ? 'Ingestion complete!' :
                     'Manually sync transactions for a date range'}
                  </div>
                  {/* Inline progress bar under subtitle - visible when running */}
                  {ingestProgress?.status === 'running' && (
                    <div className="mt-2 space-y-1">
                      <div className="w-full h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                        <motion.div
                          className="h-full bg-gradient-to-r from-blue-500 to-blue-400 rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${ingestProgress.percent ?? 0}%` }}
                          transition={{ duration: 0.5, ease: 'easeOut' }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[0.65rem] text-slate-500">
                        <span className="flex items-center gap-1">
                          <Loader2 className="h-2.5 w-2.5 animate-spin" />
                          Batch {ingestProgress.current_batch ?? '?'}/{ingestProgress.total_batches ?? '?'}
                        </span>
                        <span>{ingestProgress.percent ?? 0}%</span>
                      </div>
                    </div>
                  )}
                  {/* Completion summary */}
                  {ingestJustCompleted && ingestProgress?.result && (
                    <div className="mt-2 flex items-center gap-3 text-[0.65rem]">
                      <span className="text-emerald-400 flex items-center gap-1">
                        <Check className="h-3 w-3" />
                        {ingestProgress.result.created ?? 0} created
                      </span>
                      <span className="text-slate-400">
                        {ingestProgress.result.processed ?? 0} processed
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <button
                onClick={handleIngestNow}
                disabled={ingestProgress?.status === 'running'}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm ${
                  ingestProgress?.status === 'running'
                    ? 'bg-blue-500/20 text-blue-400 cursor-wait'
                    : ingestJustCompleted
                    ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                    : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30'
                }`}
              >
                {ingestProgress?.status === 'running' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Running...
                  </>
                ) : ingestJustCompleted ? (
                  <>
                    <Check className="h-4 w-4" />
                    Done
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    Ingest Now
                  </>
                )}
              </button>
            </div>
          </div>

      {/* Last Ingestion Info */}
          <div className="bg-slate-800/40 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="h-4 w-4 text-slate-400" />
              <span className="text-slate-300 text-sm font-medium">Last Ingestion</span>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Last Run:</span>
                <span className="text-slate-300">{formatDate(history?.last_ingestion_run)}</span>
              </div>

              {/* Tooltip-like hover info for initial sync */}
              {history?.initial_sync_date_range && (
                <div className="group relative">
                  <div className="flex items-center gap-1 text-slate-500 hover:text-slate-300 cursor-help">
                    <Info className="h-3 w-3" />
                    <span className="text-xs">Initial Sync Details</span>
                  </div>
                  <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block bg-slate-800 border border-slate-700 rounded-lg p-3 shadow-lg z-10 w-64">
                    <div className="text-xs text-slate-400 mb-1">Initial Sync Range:</div>
                    <div className="text-sm text-slate-200">{history.initial_sync_date_range}</div>
                    {history?.last_manual_ingestion_range && (
                      <>
                        <div className="text-xs text-slate-400 mt-2 mb-1">Last Manual Ingest:</div>
                        <div className="text-sm text-slate-200">{history.last_manual_ingestion_range}</div>
                        <div className="text-xs text-slate-500 mt-1">
                          {formatDate(history.last_manual_ingestion_date)}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Auto-Ingestion Settings Detailed Block */}
          <div className="bg-slate-800/40 rounded-lg p-5 border border-slate-700/50">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${autoIngestEnabled ? 'bg-emerald-500/10' : 'bg-slate-600/20'}`}>
                  <Clock className={`h-5 w-5 ${autoIngestEnabled ? 'text-emerald-400' : 'text-slate-400'}`} />
                </div>
                <div>
                  <div className="text-white font-semibold text-lg">Auto-Ingestion</div>
                  <div className="text-slate-500 text-sm">
                    {autoIngestEnabled
                      ? `Checks every ${ingestFrequency >= 60 ? `${Math.floor(ingestFrequency / 60)} hour${ingestFrequency >= 120 ? 's' : ''}${ingestFrequency % 60 > 0 ? ` ${ingestFrequency % 60} min` : ''}` : `${ingestFrequency} min`}`
                      : 'Disabled'}
                  </div>
                </div>
              </div>

              <button
                onClick={() => {
                  const newEnabled = !autoIngestEnabled;
                  setAutoIngestEnabled(newEnabled);
                  updateIngestSettingsMutation.mutate({
                    enabled: newEnabled,
                    frequency: ingestFrequency,
                  });
                }}
                disabled={updateIngestSettingsMutation.isPending}
                className={`relative w-14 h-7 rounded-full transition-colors ${
                  autoIngestEnabled ? 'bg-emerald-500' : 'bg-slate-600'
                } ${updateIngestSettingsMutation.isPending ? 'opacity-50' : ''}`}
              >
                <div
                  className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-transform shadow ${
                    autoIngestEnabled ? 'left-8' : 'left-1'
                  }`}
                />
              </button>
            </div>

            {/* Detailed Stats Grid */}
            <div className="grid grid-cols-2 gap-3 mt-4">
              {/* Last Auto Ingestion */}
              <div className="bg-slate-700/30 rounded-lg p-3">
                <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                  <RefreshCw className="h-3 w-3" />
                  Last Auto Ingestion
                </div>
                <div className="text-white text-sm">
                  {ingestSettings?.last_auto_ingestion?.timestamp
                    ? formatDate(ingestSettings.last_auto_ingestion.timestamp)
                    : 'Never'}
                </div>
                {ingestSettings?.last_auto_ingestion?.status && (
                  <div className={`flex items-center gap-1 mt-1 text-xs ${
                    ingestSettings.last_auto_ingestion.status === 'success' ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {ingestSettings.last_auto_ingestion.status === 'success' ? (
                      <CheckCircle className="h-3 w-3" />
                    ) : (
                      <XCircle className="h-3 w-3" />
                    )}
                    {ingestSettings.last_auto_ingestion.status === 'success' ? 'Completed' : 'Failed'}
                  </div>
                )}
              </div>

              {/* Next Auto Ingestion */}
              <div className="bg-slate-700/30 rounded-lg p-3">
                <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                  <Clock className="h-3 w-3" />
                  Next Auto Ingestion
                </div>
                <div className="text-white text-sm">
                  {autoIngestEnabled && ingestSettings?.next_auto_ingestion
                    ? formatDate(ingestSettings.next_auto_ingestion)
                    : autoIngestEnabled ? 'Calculating...' : 'Disabled'}
                </div>
                {ingestSettings?.last_auto_ingestion?.new_transactions !== undefined && (
                  <div className="text-xs text-slate-500 mt-1">
                    {ingestSettings.last_auto_ingestion.new_transactions} new transactions
                  </div>
                )}
              </div>

              {/* Error Message */}
              {ingestSettings?.last_auto_ingestion?.error && (
                <div className="col-span-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-red-400 text-xs mb-1">
                    <AlertCircle className="h-3 w-3" />
                    Last Error
                  </div>
                  <div className="text-red-300 text-sm">{ingestSettings.last_auto_ingestion.error}</div>
                </div>
              )}

              {/* Monthly Transactions */}
              <div className="bg-slate-700/30 rounded-lg p-3">
                <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                  <TrendingUp className="h-3 w-3" />
                  This Month
                </div>
                <div className="text-white text-2xl font-semibold">
                  {ingestSettings?.monthly_transaction_count ?? 0}
                </div>
                <div className="text-xs text-slate-500">transactions</div>
              </div>

              {/* Frequency Selector */}
              <div className="bg-slate-700/30 rounded-lg p-3">
                <div className="flex items-center gap-2 text-slate-400 text-xs mb-2">
                  <Clock className="h-3 w-3" />
                  Frequency
                </div>
                <select
                  value={ingestFrequency}
                  onChange={(e) => {
                    const freq = parseInt(e.target.value);
                    setIngestFrequency(freq);
                    updateIngestSettingsMutation.mutate({
                      enabled: autoIngestEnabled,
                      frequency: freq,
                    });
                  }}
                  disabled={updateIngestSettingsMutation.isPending}
                  className="w-full bg-slate-600 text-white text-sm rounded px-2 py-1.5 border border-slate-500 focus:border-blue-500 focus:outline-none"
                >
                  <option value={5}>Every 5 min</option>
                  <option value={15}>Every 15 min</option>
                  <option value={30}>Every 30 min</option>
                  <option value={60}>Every hour</option>
                  <option value={360}>Every 6 hours</option>
                  <option value={720}>Every 12 hours</option>
                  <option value={1440}>Daily</option>
                </select>
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* OAuth Modal — portal to body to escape parent stacking context */}
      {showOAuthModal && createPortal(
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-slate-800 rounded-xl border border-slate-700 max-w-md w-full p-6"
          >
            <h3 className="text-lg font-medium text-white mb-4">Connect Gmail</h3>

            {!oauthUrl ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
                <span className="ml-3 text-slate-400">Loading OAuth URL...</span>
              </div>
            ) : (
            <div className="space-y-4">
              <p className="text-slate-400 text-sm">
                Choose one of the following methods to connect your Gmail account:
              </p>

              {/* Method 1: Open in browser */}
              <div className="bg-slate-700/50 rounded-lg p-4">
                <div className="text-white text-sm font-medium mb-2">Method 1: Open in Browser</div>
                <p className="text-slate-400 text-xs mb-3">
                  Opens Google OAuth in a new tab. After authorization, you&apos;ll be redirected back.
                </p>
                <button
                  onClick={() => {
                    if (oauthUrl) {
                      openExternalUrl(oauthUrl);
                      setAwaitingOAuth(true);
                    }
                  }}
                  disabled={!oauthUrl}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ExternalLink className="h-4 w-4" />
                  Open OAuth Page
                </button>
              </div>

              {/* Method 2: Manual code entry */}
              <div className="bg-slate-700/50 rounded-lg p-4">
                <div className="text-white text-sm font-medium mb-2">Method 2: Manual Code</div>
                <p className="text-slate-400 text-xs mb-3">
                  If the redirect doesn&apos;t work, paste the authorization code here.
                </p>
                <div className="space-y-2">
                  <input
                    type="text"
                    value={manualCode}
                    onChange={(e) => setManualCode(e.target.value)}
                    placeholder="Paste authorization code"
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm placeholder:text-slate-500"
                  />
                  <button
                    onClick={handleManualCodeSubmit}
                    disabled={!manualCode.trim() || manualCodeMutation.isPending}
                    className="w-full px-4 py-2 bg-emerald-500/20 text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition-colors disabled:opacity-50 text-sm"
                  >
                    {manualCodeMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                    ) : (
                      'Submit Code'
                    )}
                  </button>
                </div>
              </div>
            </div>
            )}

            <button
              onClick={() => {
                setShowOAuthModal(false);
                setOauthUrl('');
              }}
              className="mt-4 w-full px-4 py-2 text-slate-400 hover:text-slate-300 transition-colors text-sm"
            >
              Cancel
            </button>
          </motion.div>
        </div>,
        document.body
      )}

      {/* Date Range Modal */}
      {showDateRangeModal && createPortal(
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-slate-800 rounded-xl border border-slate-700 max-w-md w-full p-6"
          >
            <h3 className="text-lg font-medium text-white mb-4">Ingest Transactions</h3>

            {ingestProgress?.status === 'running' ? (
              /* Running state — show progress */
              <div className="space-y-4">
                <p className="text-slate-400 text-sm">
                  Ingestion is in progress...
                </p>

                <div className="bg-slate-700/30 rounded-lg p-4">
                  <div className="flex items-center justify-between text-sm text-slate-300 mb-3">
                    <span>Batch {ingestProgress.current_batch ?? '?'} of {ingestProgress.total_batches ?? '?'}</span>
                    <span className="text-blue-400 font-medium">{ingestProgress.percent ?? 0}%</span>
                  </div>
                  <div className="w-full h-3 bg-slate-700/50 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-blue-500 to-blue-400 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${ingestProgress.percent ?? 0}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                  {ingestProgress.processed != null && (
                    <div className="text-xs text-slate-500 mt-2">
                      Processed {ingestProgress.processed} transactions
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setShowDateRangeModal(false)}
                  disabled
                  className="w-full px-4 py-2 text-slate-500 text-sm cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </button>
              </div>
            ) : ingestJustCompleted ? (
              /* Brief completed state before auto-close */
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-emerald-400">
                  <Check className="h-5 w-5" />
                  <span className="font-medium">Ingestion Complete</span>
                </div>
                {ingestProgress.result && (
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400 bg-slate-800/30 rounded-lg p-2.5">
                    <span>Processed:</span><span className="text-white/70">{ingestProgress.result.processed ?? '—'}</span>
                    <span>Created:</span><span className="text-emerald-400">{ingestProgress.result.created ?? '—'}</span>
                  </div>
                )}
              </div>
            ) : (
              /* Default state — date inputs */
              <>
                <p className="text-slate-400 text-sm mb-4">
                  Select a date range to ingest transactions. Leave blank to use default (last 7 days).
                </p>

                <div className="space-y-4">
                  <div>
                    <label className="text-slate-400 text-xs block mb-1">Start Date</label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="w-full bg-slate-700/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                    />
                  </div>

                  <div>
                    <label className="text-slate-400 text-xs block mb-1">End Date</label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="w-full bg-slate-700/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                    />
                  </div>
                </div>

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => setShowDateRangeModal(false)}
                    className="flex-1 px-4 py-2 text-slate-400 hover:text-slate-300 transition-colors text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDateRangeSubmit}
                    disabled={dateRangeMutation.isPending}
                    className="flex-1 px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors disabled:opacity-50 text-sm"
                  >
                    {dateRangeMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                    ) : (
                      'Start Ingestion'
                    )}
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </div>,
        document.body
      )}

      {/* Disconnect Confirmation Modal */}
      {showDisconnectModal && createPortal(
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-slate-800 rounded-xl border border-slate-700 max-w-md w-full p-6"
          >
            <div className="flex items-center gap-3 mb-4">
              <AlertCircle className="h-6 w-6 text-red-400" />
              <h3 className="text-lg font-medium text-white">Disconnect Gmail?</h3>
            </div>

            <p className="text-slate-400 text-sm mb-4">
              This will revoke Gmail access and stop automatic transaction syncing.
            </p>

            <div className="bg-slate-700/50 rounded-lg p-3 mb-4">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={clearDataOnDisconnect}
                  onChange={(e) => setClearDataOnDisconnect(e.target.checked)}
                  className="mt-0.5 rounded border-slate-600 bg-slate-800 text-red-500"
                />
                <div>
                  <div className="text-white text-sm">Clear all Gmail transactions</div>
                  <div className="text-slate-500 text-xs">
                    Permanently delete all transactions imported from Gmail
                  </div>
                </div>
              </label>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowDisconnectModal(false)}
                className="flex-1 px-4 py-2 text-slate-400 hover:text-slate-300 transition-colors text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleDisconnect}
                disabled={disconnectMutation.isPending}
                className="flex-1 px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors disabled:opacity-50 text-sm"
              >
                {disconnectMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                ) : (
                  'Disconnect'
                )}
              </button>
            </div>
          </motion.div>
        </div>,
        document.body
      )}
    </div>
  );
}

export default GmailSettings;
