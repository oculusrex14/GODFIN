import { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Bot, Send, AlertTriangle, User, BellRing, Mail, RefreshCw } from 'lucide-react';
import {
  fetchAdvisorDigest,
  fetchAdvisorDigestSettings,
  fetchLicenseStatus,
  sendAdvisorChat,
  sendAdvisorDigest,
  updateAdvisorDigestSettings,
} from '../api/client';

export default function Advisor() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [recipient, setRecipient] = useState('');
  const bottomRef = useRef(null);
  const queryClient = useQueryClient();
  const { data: license } = useQuery({
    queryKey: ['license'],
    queryFn: fetchLicenseStatus,
  });
  const digestAvailable = license?.features?.includes('advanced_reports') === true;
  const chatAvailable = license?.features?.includes('ai_classification') === true;
  const { data: digest, isFetching: digestLoading } = useQuery({
    queryKey: ['advisorDigest'],
    queryFn: fetchAdvisorDigest,
    enabled: digestAvailable,
  });
  const { data: digestSettings } = useQuery({
    queryKey: ['advisorDigestSettings'],
    queryFn: fetchAdvisorDigestSettings,
    enabled: digestAvailable,
  });

  const chatMutation = useMutation({
    mutationFn: sendAdvisorChat,
    onSuccess: (data) => {
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
    },
    onError: (err) => {
      const detail = err?.message || 'AI advisor unavailable. Configure an LLM provider in Settings.';
      setMessages(prev => [...prev, { role: 'assistant', content: detail, isError: true }]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const digestSettingsMutation = useMutation({
    mutationFn: updateAdvisorDigestSettings,
    onSuccess: data => queryClient.setQueryData(['advisorDigestSettings'], data),
  });
  const digestSendMutation = useMutation({
    mutationFn: sendAdvisorDigest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['advisorDigestSettings'] }),
  });
  const digestRecipient = recipient || digestSettings?.recipient || '';

  const handleSend = () => {
    const text = input.trim();
    if (!text || chatMutation.isPending || !chatAvailable) return;

    const userMsg = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');

    chatMutation.mutate({
      message: text,
      history: newMessages.filter(m => !m.isError).slice(-10),
    });
  };

  return (
    <div className="flex flex-col min-h-[calc(100vh-6rem)]">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-4">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-emerald-400/60" />
          <h1 className="text-white/90 text-[1.6rem] tracking-[-0.02em]" style={{ fontWeight: 300 }}>Financial Advisor</h1>
        </div>
        <p className="text-white/30 text-[0.8rem] mt-1">AI-powered financial guidance based on your spending data</p>
      </motion.div>

      {/* Warning banner */}
      <div className="flex items-center gap-2 bg-amber-500/[0.08] border border-amber-400/[0.15] rounded-[12px] px-3 py-2 mb-4">
        <AlertTriangle size={14} className="text-amber-400/60 shrink-0" />
        <span className="text-amber-400/70 text-[0.7rem]">Conversation is not saved. Leaving this tab will clear the chat.</span>
      </div>

      {/* Local weekly digest */}
      <div className="rounded-[20px] bg-white/[0.07] border border-white/[0.14] p-4 sm:p-5 mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-white/65 text-sm">
              <BellRing size={15} className="text-cyan-300/60" /> Weekly Digest
            </div>
            <p className="mt-1 text-white/25 text-xs">Generated locally; optional delivery uses your connected Gmail account directly.</p>
          </div>
          {digestAvailable && (
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['advisorDigest'] })}
              className="min-h-11 px-3 rounded-xl text-white/35 hover:text-white/60 hover:bg-white/[0.05] text-xs flex items-center gap-2"
            >
              <RefreshCw size={13} className={digestLoading ? 'animate-spin' : ''} /> Refresh
            </button>
          )}
        </div>

        {!digestAvailable ? (
          <p className="mt-4 text-amber-200/50 text-sm">Weekly digests are included with GODFIN Pro and Max.</p>
        ) : digest && (
          <>
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                ['This week', `₹${Math.round(digest.current_spend).toLocaleString('en-IN')}`],
                ['Velocity', digest.spending_velocity_percent == null ? 'No baseline' : `${digest.spending_velocity_percent > 0 ? '+' : ''}${digest.spending_velocity_percent}%`],
                ['Anomalies', digest.anomalies.length],
                ['Goal alerts', digest.budget_breaches.length],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-black/10 border border-white/[0.07] p-3">
                  <div className="text-white/25 text-[0.62rem] uppercase">{label}</div>
                  <div className="mt-1 text-white/65 text-sm">{value}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-white/40 text-xs">{digest.spending_velocity_message}</p>
            {digest.anomalies.length > 0 && (
              <div className="mt-3 space-y-1">
                {digest.anomalies.map(item => (
                  <div key={item.transaction_id} className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-white/40 truncate">{item.merchant}</span>
                    <span className="text-white/60 tabular-nums">₹{Math.round(item.amount).toLocaleString('en-IN')}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 pt-4 border-t border-white/[0.07]">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[210px]">
                  <Mail size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20" />
                  <input
                    type="email"
                    value={digestRecipient}
                    onChange={event => setRecipient(event.target.value)}
                    placeholder="you@example.com"
                    aria-label="Weekly digest recipient"
                    className="w-full min-h-11 rounded-xl bg-white/[0.05] border border-white/[0.1] pl-9 pr-3 text-white/65 text-xs outline-none focus:border-cyan-400/25"
                  />
                </div>
                <button
                  onClick={() => digestSettingsMutation.mutate({
                    enabled: !digestSettings?.enabled,
                    recipient: digestRecipient,
                  })}
                  disabled={!digestRecipient.includes('@') || digestSettingsMutation.isPending}
                  className={`min-h-11 px-3 rounded-xl border text-xs ${
                    digestSettings?.enabled
                      ? 'bg-emerald-400/10 border-emerald-400/20 text-emerald-200/75'
                      : 'bg-white/[0.05] border-white/[0.1] text-white/45'
                  } disabled:opacity-35`}
                >
                  {digestSettings?.enabled ? 'Weekly email on' : 'Enable weekly email'}
                </button>
                <button
                  onClick={() => digestSendMutation.mutate()}
                  disabled={!digestSettings?.enabled || digestSendMutation.isPending}
                  className="min-h-11 px-3 rounded-xl bg-white/[0.05] border border-white/[0.1] text-white/45 text-xs disabled:opacity-35"
                >
                  Send now
                </button>
              </div>
              {digestSettings && (!digestSettings.gmail_connected || !digestSettings.gmail_send_supported) && (
                <p className="mt-2 text-amber-200/45 text-xs">Reconnect Gmail in Settings to grant optional digest-send access.</p>
              )}
            </div>
          </>
        )}
      </div>

      {/* Chat messages */}
      <div className="flex-1 min-h-[320px] overflow-y-auto space-y-3 pr-1 mb-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Bot className="h-12 w-12 text-white/10 mb-3" />
            <p className="text-white/30 text-[0.85rem]">Ask me anything about your finances.</p>
            {!chatAvailable && (
              <p className="mt-2 text-amber-200/45 text-xs">Advisor chat is available with GODFIN Pro or Max.</p>
            )}
            <div className="mt-4 flex flex-wrap gap-2 justify-center">
              {[
                'How can I save more?',
                'Analyze my spending',
                'Am I on track with my goals?',
                'Where am I overspending?',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => { setInput(suggestion); }}
                  disabled={!chatAvailable}
                  className="text-[0.75rem] text-cyan-400/60 bg-cyan-400/[0.06] border border-cyan-400/[0.12] rounded-full px-3 py-1.5 hover:bg-cyan-400/[0.12] transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <Bot size={14} className="text-emerald-400/60" />
              </div>
            )}
            <div className={`max-w-[80%] rounded-[16px] px-4 py-2.5 text-[0.85rem] leading-relaxed ${
              msg.role === 'user'
                ? 'bg-cyan-500/15 text-white/80 border border-cyan-400/10'
                : msg.isError
                  ? 'bg-rose-500/10 text-rose-400/80 border border-rose-400/10'
                  : 'bg-white/[0.06] text-white/70 border border-white/[0.08]'
            }`}>
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-cyan-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <User size={14} className="text-cyan-400/60" />
              </div>
            )}
          </motion.div>
        ))}

        {chatMutation.isPending && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-emerald-400/60 animate-pulse" />
            </div>
            <div className="bg-white/[0.06] border border-white/[0.08] rounded-[16px] px-4 py-2.5">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-white/20 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="relative">
        <input
          aria-label="Ask the financial advisor"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Ask about your finances..."
          className="w-full bg-white/[0.06] border border-white/[0.12] rounded-[16px] pl-4 pr-12 py-3 text-[0.85rem] text-white/80 placeholder:text-white/20 outline-none focus:border-white/[0.2] transition-colors"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || chatMutation.isPending || !chatAvailable}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-[10px] bg-emerald-500/20 text-emerald-400/80 hover:bg-emerald-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          aria-label="Send advisor message"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
