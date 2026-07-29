import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import { AlertCircle, Check, ChevronDown, Loader2, MessageCircle, X, Send, Bot, User, ArrowDownLeft } from 'lucide-react';
import { fetchReviewQueue, resolveReviewItem, fetchCategories, sendReviewChat } from '../api/client';
import { GlassButton } from '../components/GlassButton';

function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function getInitialMessage(item) {
  const name = item.merchant_normalized || item.merchant_raw;
  return [{ role: 'assistant', content: `I'll help you classify this transaction. Can you tell me what "${name}" is? For example, is it a restaurant, a shop, a subscription, etc.?` }];
}

function ChatModal({ item, onClose, onClassify }) {
  const [messages, setMessages] = useState(() => getInitialMessage(item));
  const [input, setInput] = useState('');
  const [pendingOptions, setPendingOptions] = useState([]);
  const bottomRef = useRef(null);

  const chatMutation = useMutation({
    mutationFn: sendReviewChat,
    onSuccess: (data) => {
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
      if (data.options && data.options.length > 0) {
        setPendingOptions(data.options);
      }
    },
    onError: (err) => {
      const detail = err?.message || 'AI unavailable. Configure an LLM provider in Settings.';
      setMessages(prev => [...prev, { role: 'assistant', content: detail, isError: true }]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingOptions]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || chatMutation.isPending) return;

    const userMsg = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setPendingOptions([]);

    chatMutation.mutate({
      transactionId: item.id,
      message: text,
      history: newMessages.filter(m => !m.isError).slice(-10),
    });
  };

  const handlePickOption = (option) => {
    onClassify(item.id, option.category, option.subcategory || null);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="w-full max-w-lg max-h-[80vh] flex flex-col rounded-[20px] bg-[#0f1a2e]/95 backdrop-blur-[32px] border border-white/[0.15] shadow-[0_24px_80px_rgba(0,0,0,0.4)]"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.08]">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-[10px] bg-cyan-500/10 border border-cyan-400/15 flex items-center justify-center shrink-0">
              <MessageCircle size={16} className="text-cyan-400/70" />
            </div>
            <div className="min-w-0">
              <p className="text-white/80 text-[0.85rem] truncate" style={{ fontWeight: 500 }}>
                {item.merchant_normalized || item.merchant_raw}
              </p>
              <p className="text-white/30 text-[0.7rem]">
                {format(new Date(item.date), 'dd MMM yyyy')} · {item.type === 'credit' ? '+' : '-'}{formatINR(item.amount)}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-[8px] hover:bg-white/[0.06] transition-colors">
            <X size={16} className="text-white/40" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-6 h-6 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Bot size={12} className="text-emerald-400/60" />
                </div>
              )}
              <div className={`max-w-[80%] rounded-[14px] px-3.5 py-2 text-[0.8rem] leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-cyan-500/15 text-white/80 border border-cyan-400/10'
                  : msg.isError
                    ? 'bg-rose-500/10 text-rose-400/80 border border-rose-400/10'
                    : 'bg-white/[0.06] text-white/70 border border-white/[0.08]'
              }`}>
                {msg.content}
              </div>
              {msg.role === 'user' && (
                <div className="w-6 h-6 rounded-full bg-cyan-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <User size={12} className="text-cyan-400/60" />
                </div>
              )}
            </motion.div>
          ))}

          {chatMutation.isPending && (
            <div className="flex gap-2.5">
              <div className="w-6 h-6 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0">
                <Bot size={12} className="text-emerald-400/60 animate-pulse" />
              </div>
              <div className="bg-white/[0.06] border border-white/[0.08] rounded-[14px] px-3.5 py-2">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          {/* Classification options */}
          {pendingOptions.length > 0 && !chatMutation.isPending && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="pt-2">
              <p className="text-white/30 text-[0.7rem] mb-2">Pick a classification:</p>
              <div className="space-y-2">
                {pendingOptions.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => handlePickOption(opt)}
                    className="w-full text-left px-4 py-3 rounded-[12px] bg-white/[0.04] border border-white/[0.1] hover:bg-cyan-500/10 hover:border-cyan-400/20 transition-all group"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-white/80 text-[0.8rem] group-hover:text-cyan-300 transition-colors" style={{ fontWeight: 500 }}>
                          {opt.category}
                        </span>
                        {opt.subcategory && (
                          <span className="text-white/40 text-[0.75rem] ml-2">/ {opt.subcategory}</span>
                        )}
                      </div>
                      {opt.confidence != null && (
                        <span className="text-white/25 text-[0.7rem] tabular-nums">
                          {(opt.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-5 py-3 border-t border-white/[0.08]">
          <div className="relative">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Describe this transaction..."
              className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[12px] pl-4 pr-11 py-2.5 text-[0.8rem] text-white/80 placeholder:text-white/20 outline-none focus:border-white/[0.2] transition-colors"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || chatMutation.isPending}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-[8px] bg-cyan-500/20 text-cyan-400/80 hover:bg-cyan-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function ReviewQueue() {
  const [expandedId, setExpandedId] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState({});
  const [selectedSubcategory, setSelectedSubcategory] = useState({});
  const [typeFilter, setTypeFilter] = useState('');
  const [chatItem, setChatItem] = useState(null);
  const queryClient = useQueryClient();

  const { data: reviewData, isLoading } = useQuery({
    queryKey: ['reviewQueue'],
    queryFn: () => fetchReviewQueue({ page: 1, page_size: 50 }),
  });

  const { data: categories } = useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
  });

  const resolveMutation = useMutation({
    mutationFn: ({ transactionId, category, subcategory }) =>
      resolveReviewItem(transactionId, category, subcategory),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['categoryBreakdown'] });
      queryClient.invalidateQueries({ queryKey: ['incomeStats'] });
      queryClient.invalidateQueries({ queryKey: ['incomeSources'] });
      setSelectedCategory(prev => { const next = { ...prev }; delete next[variables.transactionId]; return next; });
      setSelectedSubcategory(prev => { const next = { ...prev }; delete next[variables.transactionId]; return next; });
      setExpandedId(null);
      setChatItem(null);
    },
  });

  const handleCategorySelect = (transactionId, category) => {
    setSelectedCategory(prev => ({ ...prev, [transactionId]: category }));
    setSelectedSubcategory(prev => ({ ...prev, [transactionId]: '' }));
  };

  const handleSubcategorySelect = (transactionId, subcategory) => {
    setSelectedSubcategory(prev => ({ ...prev, [transactionId]: subcategory }));
  };

  const handleResolve = (transactionId) => {
    const category = selectedCategory[transactionId];
    const subcategory = selectedSubcategory[transactionId] || null;
    if (category) {
      resolveMutation.mutate({ transactionId, category, subcategory });
    }
  };

  const handleChatClassify = (transactionId, category, subcategory) => {
    resolveMutation.mutate({ transactionId, category, subcategory });
  };

  const items = (reviewData?.items || []).filter(item =>
    !typeFilter || item.type === typeFilter
  );

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Review Queue</h1>
            <p className="text-white/30 text-[0.8rem]">
              {items.length > 0 ? `${items.length} transaction${items.length !== 1 ? 's' : ''} need categorization` : 'All transactions categorized!'}
            </p>
          </div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="Filter by transaction type"
            className="bg-white/[0.06] border border-white/[0.12] rounded-[10px] px-3 py-2 text-[0.8rem] text-white/70 focus:outline-none focus:border-cyan-400/30"
          >
            <option value="" className="bg-[#1a2a4a]">All Types</option>
            <option value="debit" className="bg-[#1a2a4a]">Debit</option>
            <option value="credit" className="bg-[#1a2a4a]">Credit</option>
          </select>
        </div>
      </motion.div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-white/30" />
        </div>
      ) : items.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-16 text-white/30">
          <Check className="h-12 w-12 mb-4 text-emerald-400/60" />
          <p className="text-[1.1rem]" style={{ fontWeight: 400 }}>All caught up!</p>
          <p className="text-[0.85rem] text-white/20">No transactions need review right now.</p>
        </motion.div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {items.map((item, index) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -100 }}
                transition={{ delay: index * 0.05 }}
                className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]"
              >
                <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
                <div
                  onClick={() => {
                    const newId = expandedId === item.id ? null : item.id;
                    setExpandedId(newId);
                    // Auto-suggest INCOME for credit transactions
                    if (newId && item.type === 'credit' && !selectedCategory[item.id]) {
                      handleCategorySelect(item.id, 'INCOME');
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const newId = expandedId === item.id ? null : item.id;
                      setExpandedId(newId);
                      if (newId && item.type === 'credit' && !selectedCategory[item.id]) {
                        handleCategorySelect(item.id, 'INCOME');
                      }
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-expanded={expandedId === item.id}
                  aria-label={`Review transaction: ${item.merchant_normalized || item.merchant_raw}, ${formatINR(item.amount)}`}
                  className="flex items-center justify-between p-4 cursor-pointer hover:bg-white/[0.03] transition-colors focus:outline-none focus:bg-white/[0.05]"
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-[14px] ${item.type === 'credit' ? 'bg-emerald-400/[0.1] border border-emerald-400/[0.12]' : 'bg-amber-400/[0.1] border border-amber-400/[0.12]'} flex items-center justify-center`}>
                      {item.type === 'credit' ? (
                        <ArrowDownLeft className="h-5 w-5 text-emerald-400/70" aria-hidden="true" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-amber-400/70" aria-hidden="true" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-white/80 text-[0.9rem]" style={{ fontWeight: 400 }}>{item.merchant_normalized || item.merchant_raw}</p>
                        {item.type === 'credit' && (
                          <span className="px-1.5 py-0.5 text-[0.6rem] rounded-md bg-emerald-500/15 text-emerald-400/80 border border-emerald-400/15" style={{ fontWeight: 600 }}>INCOME</span>
                        )}
                      </div>
                      <p className="text-white/30 text-[0.75rem]">
                        {format(new Date(item.date), 'dd MMM yyyy')} · {item.instrument}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); setChatItem(item); }}
                      title="Ask AI to classify"
                      className="p-2 rounded-[10px] bg-cyan-500/[0.08] border border-cyan-400/[0.12] text-cyan-400/60 hover:bg-cyan-500/[0.15] hover:text-cyan-400/80 transition-all"
                    >
                      <MessageCircle size={16} />
                    </button>
                    <span className={`text-[1rem] tabular-nums ${item.type === 'credit' ? 'text-emerald-400/80' : 'text-white/70'}`} style={{ fontWeight: 500 }}>
                      {item.type === 'credit' ? '+' : '-'}{formatINR(item.amount)}
                    </span>
                    <ChevronDown className={`h-4 w-4 text-white/30 transition-transform ${expandedId === item.id ? 'rotate-180' : ''}`} aria-hidden="true" />
                  </div>
                </div>

                <AnimatePresence>
                  {expandedId === item.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="border-t border-white/[0.06]"
                    >
                      <div className="p-4 bg-white/[0.02]">
                        <p className="text-white/25 text-[0.7rem] mb-3">Select a category:</p>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mb-4">
                          {categories && Object.keys(categories).map((cat) => (
                            <button
                              key={cat}
                              onClick={() => handleCategorySelect(item.id, cat)}
                              className={`px-3 py-2 text-[0.75rem] rounded-[10px] transition-all ${
                                selectedCategory[item.id] === cat
                                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/30'
                                  : 'bg-white/[0.04] text-white/50 border border-white/[0.06] hover:bg-white/[0.08]'
                              }`}
                              style={{ fontWeight: 500 }}
                            >
                              {cat}
                            </button>
                          ))}
                        </div>

                        {selectedCategory[item.id] && categories[selectedCategory[item.id]] && (
                          <div className="mb-4">
                            <p className="text-white/25 text-[0.7rem] mb-2">Select a subcategory (optional):</p>
                            <select
                              value={selectedSubcategory[item.id] || ''}
                              onChange={(e) => handleSubcategorySelect(item.id, e.target.value)}
                              aria-label={`Subcategory for ${selectedCategory[item.id]}`}
                              className="bg-white/[0.06] border border-white/[0.12] rounded-[10px] px-3 py-2 text-[0.8rem] text-white/70 focus:outline-none focus:border-cyan-400/30"
                            >
                              <option value="" className="bg-[#1a2a4a]">No subcategory</option>
                              {categories[selectedCategory[item.id]].map((sub) => (
                                <option key={sub} value={sub} className="bg-[#1a2a4a]">{sub}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {selectedCategory[item.id] && (
                          <GlassButton onClick={() => handleResolve(item.id)} disabled={resolveMutation.isPending}>
                            {resolveMutation.isPending ? 'Saving...' : 'Confirm Classification'}
                          </GlassButton>
                        )}

                        <div className="mt-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
                          <p className="text-white/30 text-[0.65rem] uppercase tracking-wide">Why this needs review</p>
                          <p className="mt-1 text-white/40 text-[0.7rem] leading-relaxed">
                            {item.classification_reason}
                            {item.confidence > 0 && ` Confidence: ${(item.confidence * 100).toFixed(0)}%.`}
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Chat Modal */}
      <AnimatePresence>
        {chatItem && (
          <ChatModal
            item={chatItem}
            onClose={() => setChatItem(null)}
            onClassify={handleChatClassify}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
