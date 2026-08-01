import { useState, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Cpu, Loader2, Check, AlertCircle, RefreshCw, ExternalLink,
  Key, Server, ChevronDown, Info, Trash2, Edit2, Plus
} from 'lucide-react';
import {
  fetchLLMConfig,
  fetchLLMProviders,
  createLLMConfig,
  updateLLMConfig,
  deleteLLMConfig,
  testLLMConnection,
} from '../../api/llm';
import { GlassButton } from '../GlassButton';

// Static glassmorphism style constants - defined at module level to avoid recreating on every render
const GLASS_INPUT = 'bg-white/[0.08] backdrop-blur-[16px] border border-white/[0.15] text-white/80 text-[0.8rem] rounded-[14px] px-4 py-2.5 focus:outline-none focus:border-cyan-400/30 transition-all';
const GLASS_INPUT_HOVER = 'hover:bg-white/[0.12]';
const GLASS_BUTTON_BASE = 'bg-white/[0.08] backdrop-blur-[12px] text-white/70 border border-white/[0.12] rounded-[14px] hover:bg-white/[0.12] hover:text-white transition-all text-[0.8rem]';
const GLASS_BUTTON_PRIMARY = 'bg-cyan-500/20 text-cyan-300 border-cyan-400/30 shadow-[0_0_16px_rgba(34,211,238,0.1)] hover:bg-cyan-500/30';
const GLASS_CARD = 'relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]';
const GLASS_GRADIENT_LINE = 'absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent';
const GLASS_CARD_ACTIVE = 'relative overflow-hidden rounded-[16px] bg-white/[0.08] backdrop-blur-[16px] border border-emerald-500/30 shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.1)]';
const GLASS_GRADIENT_LINE_EMERALD = 'absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-emerald-400/30 to-transparent';
const GLASS_CARD_INACTIVE = 'relative overflow-hidden rounded-[16px] bg-white/[0.06] backdrop-blur-[16px] border border-white/[0.12] shadow-[0_8px_32px_rgba(0,0,0,0.06)]';
const GLASS_GRADIENT_LINE_SUBTLE = 'absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent';

// Provider display names
const PROVIDER_NAMES = {
  ollama_local: 'Ollama (Local)',
  ollama_cloud: 'Ollama (Cloud)',
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  gemini: 'Google Gemini',
  moonshot: 'Kimi (Moonshot)',
  zai: 'GLM (Z.AI)',
  deepseek: 'Deepseek',
  qwen: 'Qwen',
  minimax: 'Minimax',
};

// Authentication method labels
const AUTH_METHODS = {
  oauth: 'OAuth',
  openapi: 'API Key',
  none: 'No Authentication',
};

function LLMSettings() {
  const queryClient = useQueryClient();
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [toast, setToast] = useState(null);

  // Form state
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedAuth, setSelectedAuth] = useState('openapi');
  const [selectedModel, setSelectedModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [hostedConsent, setHostedConsent] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Memoized handlers to prevent unnecessary re-renders
  const showToast = useCallback((msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const resetForm = useCallback(() => {
    setSelectedProvider('');
    setSelectedAuth('openapi');
    setSelectedModel('');
    setApiKey('');
    setBaseUrl('');
    setHostedConsent(false);
    setTestResult(null);
  }, []);

  const handleAddNew = useCallback(() => {
    resetForm();
    setEditingConfig(null);
    setShowConfigModal(true);
  }, [resetForm]);

  const handleEdit = useCallback((config) => {
    setEditingConfig(config);
    setSelectedProvider(config.provider);
    setSelectedAuth(config.auth_method);
    setSelectedModel(config.model);
    setBaseUrl(config.base_url || '');
    setApiKey(''); // Don't show existing API key
    setHostedConsent(config.hosted_data_consent === true);
    setShowConfigModal(true);
  }, []);

  const handleCloseModal = useCallback(() => {
    setShowConfigModal(false);
    resetForm();
    setEditingConfig(null);
  }, [resetForm]);

  // Fetch current config and providers
  const { data: currentConfig } = useQuery({
    queryKey: ['llmConfig'],
    queryFn: fetchLLMConfig,
  });

  const { data: providersData, isLoading: providersLoading, error: providersError } = useQuery({
    queryKey: ['llmProviders'],
    queryFn: fetchLLMProviders,
  });

  const createMutation = useMutation({
    mutationFn: createLLMConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llmConfig'] });
      setShowConfigModal(false);
      resetForm();
      showToast('LLM configuration saved successfully');
    },
    onError: (err) => showToast(err.message, 'error'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => updateLLMConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llmConfig'] });
      setShowConfigModal(false);
      setEditingConfig(null);
      resetForm();
      showToast('Configuration updated successfully');
    },
    onError: (err) => showToast(err.message, 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteLLMConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llmConfig'] });
      showToast('Configuration deleted');
    },
    onError: (err) => showToast(err.message, 'error'),
  });

  // Get available auth methods for selected provider
  const availableAuthMethods = useMemo(() => {
    if (!selectedProvider || !providersData) return ['openapi'];
    const provider = providersData[selectedProvider];
    return provider?.auth_methods || ['openapi'];
  }, [selectedProvider, providersData]);

  // Get available models for selected provider
  const availableModels = useMemo(() => {
    if (!selectedProvider || !providersData) return [];
    const provider = providersData[selectedProvider];
    const models = provider?.models;

    if (!models) return [];

    // Handle manual entry (Ollama Local)
    if (models.manual) {
      return { manual: true, suggestions: models.suggestions || [] };
    }

    // Handle tiered models
    if (models.top) {
      return [
        { value: models.top, label: 'Top Tier', tier: 'top' },
        { value: models.mid, label: 'Mid Tier', tier: 'mid' },
        { value: models.light, label: 'Lightweight', tier: 'light' },
      ];
    }

    // Handle simple array
    return models.map(m => ({ value: m, label: m }));
  }, [selectedProvider, providersData]);

  // Handle provider change - memoized
  const handleProviderChange = useCallback((provider) => {
    setSelectedProvider(provider);
    setSelectedModel('');
    setTestResult(null);
    setHostedConsent(false);

    // Set default auth method
    const providerInfo = providersData?.[provider];
    if (providerInfo?.auth_methods?.length > 0) {
      setSelectedAuth(providerInfo.auth_methods[0]);
    }

    // Set default base URL for Ollama Local
    if (provider === 'ollama_local') {
      setBaseUrl('http://localhost:11434');
    } else {
      setBaseUrl('');
    }
  }, [providersData]);

  // Test connection - memoized to prevent unnecessary re-renders
  const handleTestConnection = useCallback(async () => {
    if (!selectedProvider || !selectedModel) {
      showToast('Please select provider and model', 'error');
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      const result = await testLLMConnection({
        provider: selectedProvider,
        model: selectedModel,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
      });
      setTestResult(result);
    } catch (err) {
      setTestResult({ success: false, message: err.message });
    } finally {
      setIsTesting(false);
    }
  }, [selectedProvider, selectedModel, apiKey, baseUrl, showToast]);

  // Save configuration - memoized
  const handleSave = useCallback(() => {
    if (!selectedProvider || !selectedModel) {
      showToast('Provider and model are required', 'error');
      return;
    }

    // Check if API key is required
    const providerInfo = providersData?.[selectedProvider];
    if (providerInfo?.requires_auth && !apiKey && !editingConfig?.has_api_key) {
      showToast('API key is required for this provider', 'error');
      return;
    }
    if (providerInfo?.is_local === false && !hostedConsent) {
      showToast('Review and accept the hosted AI data disclosure', 'error');
      return;
    }

    const data = {
      provider: selectedProvider,
      auth_method: selectedAuth,
      model: selectedModel,
      api_key: apiKey || undefined,
      base_url: baseUrl || undefined,
      hosted_data_consent: providerInfo?.is_local === false ? hostedConsent : false,
    };

    if (editingConfig) {
      updateMutation.mutate({ id: editingConfig.id, data });
    } else {
      createMutation.mutate(data);
    }
  }, [selectedProvider, selectedModel, selectedAuth, apiKey, baseUrl, hostedConsent, providersData, editingConfig, updateMutation, createMutation, showToast]);

  // Get tier badge color
  const getTierColor = (tier) => {
    switch (tier) {
      case 'top': return 'bg-amber-500/20 text-amber-400';
      case 'mid': return 'bg-blue-500/20 text-blue-400';
      case 'light': return 'bg-slate-500/20 text-slate-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
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
            className={`px-4 py-2.5 rounded-[12px] text-[0.8rem] border backdrop-blur-[16px] ${
              toast.type === 'error'
                ? 'bg-rose-500/10 border-rose-400/30 text-rose-300'
                : 'bg-emerald-500/10 border-emerald-400/30 text-emerald-300'
            }`}
          >
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Current Config Card */}
      {currentConfig ? (
        <div className={GLASS_CARD_ACTIVE}>
          <div className={GLASS_GRADIENT_LINE_EMERALD} />
          <div className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-[12px] bg-emerald-500/20 backdrop-blur-[8px]">
                <Cpu className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <div className="text-white/90 text-[0.9rem] flex items-center gap-2" style={{ fontWeight: 500 }}>
                  {PROVIDER_NAMES[currentConfig.provider] || currentConfig.provider}
                  <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-[0.7rem] rounded-full border border-emerald-400/20">
                    {!currentConfig.is_local && !currentConfig.hosted_data_consent ? 'Paused' : 'Active'}
                  </span>
                </div>
                <div className="text-white/40 text-[0.75rem]">
                  Model: {currentConfig.model} • Auth: {AUTH_METHODS[currentConfig.auth_method]}
                </div>
                {!currentConfig.is_local && !currentConfig.hosted_data_consent && (
                  <div className="mt-1 text-amber-300/70 text-[0.72rem]">
                    Paused until the hosted-data disclosure is accepted
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => handleEdit(currentConfig)}
                className="p-2 text-white/40 hover:text-white/80 transition-colors rounded-[10px] hover:bg-white/[0.08]"
                title="Edit configuration"
              >
                <Edit2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => deleteMutation.mutate(currentConfig.id)}
                disabled={deleteMutation.isPending}
                className="p-2 text-white/40 hover:text-rose-400 transition-colors rounded-[10px] hover:bg-rose-500/10"
                title="Delete configuration"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className={GLASS_CARD_INACTIVE}>
          <div className={GLASS_GRADIENT_LINE_SUBTLE} />
          <div className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-[12px] bg-white/[0.08]">
                <Cpu className="h-5 w-5 text-white/50" />
              </div>
              <div>
                <div className="text-white/80 text-[0.9rem]" style={{ fontWeight: 500 }}>No LLM Configured</div>
                <div className="text-white/30 text-[0.75rem]">
                  Configure an LLM provider for AI-powered classification
                </div>
              </div>
            </div>

            <button
              onClick={handleAddNew}
              className="flex items-center gap-2 px-4 py-2 bg-cyan-500/20 text-cyan-300 rounded-[14px] hover:bg-cyan-500/30 transition-all text-[0.8rem] border border-cyan-400/30 backdrop-blur-[12px] shadow-[0_0_16px_rgba(34,211,238,0.1)]"
            >
              <Plus className="h-4 w-4" />
              Configure LLM
            </button>
          </div>
        </div>
      )}

      {/* Add/Change Button */}
      {currentConfig && (
        <div className="flex justify-end">
          <button
            onClick={handleAddNew}
            className={`flex items-center gap-2 px-4 py-2 ${GLASS_BUTTON_BASE}`}
          >
            <RefreshCw className="h-4 w-4" />
            Change Provider
          </button>
        </div>
      )}

      {/* Configuration Modal — portal to body to escape parent overflow/stacking context */}
      {showConfigModal && createPortal(
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative rounded-[20px] bg-[#0d1f3c]/95 backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.1)] max-w-lg w-full max-h-[85vh] overflow-y-auto"
          >
            <div className={GLASS_GRADIENT_LINE} />
            <div className="p-6">
              <h3 className="text-[1.1rem] text-white/90 mb-1" style={{ fontWeight: 500 }}>
                {editingConfig ? 'Edit LLM Configuration' : 'Configure LLM Provider'}
              </h3>
              <p className="text-white/40 text-[0.8rem] mb-6">
                Select an AI provider for transaction classification
              </p>

              <div className="space-y-5">
                {/* Provider Selection */}
                <div>
                  <label className="text-white/50 text-[0.8rem] block mb-2">
                    Provider
                    {providersLoading && <span className="ml-2 text-white/30">(Loading...)</span>}
                  </label>
                  <div className="relative">
                    <select
                      value={selectedProvider}
                      onChange={(e) => handleProviderChange(e.target.value)}
                      className={`w-full appearance-none ${GLASS_INPUT} ${GLASS_INPUT_HOVER} cursor-pointer disabled:opacity-50`}
                      disabled={!!editingConfig || providersLoading}
                    >
                      <option value="" className="bg-[#1a2a4a] text-white">
                        {providersLoading ? 'Loading providers...' : 'Select a provider...'}
                      </option>
                      {providersData && Object.entries(providersData).map(([key, info]) => (
                        <option key={key} value={key} className="bg-[#1a2a4a] text-white">
                          {info.name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
                  </div>
                  {providersError && (
                    <p className="text-rose-400/80 text-[0.75rem] mt-1">
                      Error loading providers. Please check console.
                    </p>
                  )}
                  {selectedProvider && providersData?.[selectedProvider]?.description && (
                    <p className="text-white/30 text-[0.75rem] mt-1">
                      {providersData[selectedProvider].description}
                    </p>
                  )}
                </div>

                {/* Authentication Method */}
                {selectedProvider && (
                  <div>
                    <label className="text-white/50 text-[0.8rem] block mb-2">
                      Authentication Method
                    </label>
                    <div className="flex gap-2">
                      {availableAuthMethods.map((method) => (
                        <button
                          key={method}
                          onClick={() => setSelectedAuth(method)}
                          disabled={selectedProvider === 'ollama_local'}
                          className={`flex-1 px-3 py-2 rounded-[14px] text-[0.8rem] transition-all backdrop-blur-[12px] border ${
                            selectedAuth === method
                              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/30 shadow-[0_0_16px_rgba(34,211,238,0.1)]'
                              : 'bg-white/[0.08] text-white/60 border-white/[0.12] hover:bg-white/[0.12] hover:text-white/80'
                          } ${selectedProvider === 'ollama_local' ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          {AUTH_METHODS[method]}
                        </button>
                      ))}
                    </div>
                    {selectedProvider === 'ollama_local' && (
                      <p className="text-white/30 text-[0.75rem] mt-1">
                        Ollama Local does not require authentication
                      </p>
                    )}
                  </div>
                )}

                {/* Model Selection */}
                {selectedProvider && availableModels && (
                  <div>
                    <label className="text-white/50 text-[0.8rem] block mb-2">
                      Model
                    </label>

                    {availableModels.manual ? (
                      // Manual entry for Ollama Local
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                          placeholder="e.g., llama3.1:8b"
                          className={`w-full ${GLASS_INPUT} ${GLASS_INPUT_HOVER}`}
                        />
                        <div className="flex flex-wrap gap-1">
                          {availableModels.suggestions.map((suggestion) => (
                            <button
                              key={suggestion}
                              onClick={() => setSelectedModel(suggestion)}
                              className="text-[0.75rem] px-2.5 py-1 bg-white/[0.08] text-white/50 rounded-[10px] hover:bg-white/[0.12] hover:text-white/70 transition-all border border-white/[0.08]"
                              title="Click to use this model"
                            >
                              {suggestion}
                            </button>
                          ))}
                        </div>
                        <p className="text-white/30 text-[0.75rem]">
                          Enter model name or click a suggestion. Format: name:tag
                        </p>
                      </div>
                    ) : (
                      // Dropdown for other providers
                      <div className="space-y-2">
                        {availableModels.map((model) => (
                          <button
                            key={model.value}
                            onClick={() => setSelectedModel(model.value)}
                            className={`w-full flex items-center justify-between px-3 py-2 rounded-[14px] text-[0.8rem] transition-all backdrop-blur-[12px] border ${
                              selectedModel === model.value
                                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/30 shadow-[0_0_16px_rgba(34,211,238,0.1)]'
                                : 'bg-white/[0.08] text-white/70 border-white/[0.12] hover:bg-white/[0.12] hover:text-white'
                            }`}
                          >
                            <span>{model.label}</span>
                            {model.tier && (
                              <span className={`px-2 py-0.5 rounded-full text-[0.65rem] ${getTierColor(model.tier)}`}>
                                {model.tier}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Base URL (for Ollama) */}
                {selectedProvider?.includes('ollama') && (
                  <div>
                    <label className="text-white/50 text-[0.8rem] block mb-2 flex items-center gap-1">
                      <Server className="h-3 w-3" />
                      Base URL
                    </label>
                    <input
                      type="text"
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder={selectedProvider === 'ollama_local' ? 'http://localhost:11434' : 'https://api.ollama.com'}
                      className={`w-full ${GLASS_INPUT} ${GLASS_INPUT_HOVER}`}
                    />
                  </div>
                )}

                {/* API Key */}
                {selectedProvider && selectedAuth === 'openapi' && providersData?.[selectedProvider]?.requires_auth && (
                  <div>
                    <label className="text-white/50 text-[0.8rem] block mb-2 flex items-center gap-1">
                      <Key className="h-3 w-3" />
                      API Key
                      {editingConfig?.has_api_key && (
                        <span className="text-white/30">(leave blank to keep existing)</span>
                      )}
                    </label>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="Enter your API key"
                      className={`w-full ${GLASS_INPUT} ${GLASS_INPUT_HOVER}`}
                    />
                    <p className="text-white/30 text-[0.7rem] mt-1">
                      Your API key is stored securely and never displayed
                    </p>
                  </div>
                )}

                {selectedProvider && providersData?.[selectedProvider]?.is_local === false && (
                  <label className="flex items-start gap-3 rounded-[14px] border border-amber-300/20 bg-amber-400/[0.06] p-3 text-white/55 text-[0.78rem] leading-relaxed">
                    <input
                      type="checkbox"
                      checked={hostedConsent}
                      onChange={(event) => setHostedConsent(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      I understand that GODFIN will send redacted financial context to this provider when I use AI. GODFIN removes account details, payment addresses, phone numbers, references, exact dates, and exact amounts; the provider’s own privacy terms still apply.
                    </span>
                  </label>
                )}

                {/* Test Connection */}
                {selectedProvider && selectedModel && (
                  <div className="pt-4 border-t border-white/[0.08]">
                    <button
                      onClick={handleTestConnection}
                      disabled={isTesting}
                      className={`w-full flex items-center justify-center gap-2 ${GLASS_BUTTON_BASE} disabled:opacity-50`}
                    >
                      {isTesting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ExternalLink className="h-4 w-4" />
                      )}
                      Test Connection
                    </button>

                    {testResult && (
                      <div className={`mt-3 p-3 rounded-[12px] text-[0.8rem] border backdrop-blur-[12px] ${
                        testResult.success
                          ? 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30'
                          : 'bg-rose-500/10 text-rose-300 border-rose-400/30'
                      }`}>
                        <div className="flex items-start gap-2">
                          {testResult.success ? (
                            <Check className="h-4 w-4 shrink-0 mt-0.5" />
                          ) : (
                            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                          )}
                          <span>{testResult.message}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-3 mt-6 pt-4 border-t border-white/[0.08]">
                <button
                  onClick={handleCloseModal}
                  className={`flex-1 ${GLASS_BUTTON_BASE}`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={!selectedProvider || !selectedModel || createMutation.isPending || updateMutation.isPending}
                  className={`flex-1 ${GLASS_BUTTON_BASE} ${GLASS_BUTTON_PRIMARY}`}
                >
                  {createMutation.isPending || updateMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                  ) : (
                    editingConfig ? 'Update' : 'Save Configuration'
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        </div>,
        document.body
      )}
    </div>
  );
}

export default LLMSettings;
