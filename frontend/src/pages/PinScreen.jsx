import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, ShieldAlert } from 'lucide-react';
import PinInput from '../components/PinInput';
import { useAuth } from '../context/AuthContext';
import { fetchHealth, setPin, verifyPin } from '../api/client';

export default function PinScreen() {
  const { isFirstRun, handleAuth } = useAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState(true);
  const [pin, setPinValue] = useState('');
  const [retryAfter, setRetryAfter] = useState(0);

  // Poll backend health every 3 seconds
  useEffect(() => {
    let cancelled = false;
    async function checkHealth() {
      try {
        const data = await fetchHealth({ signal: AbortSignal.timeout(3000) });
        if (cancelled) return;
        const online = data.status === 'ok';
        setBackendOnline(prev => {
          if (!prev && online) {
            // Backend just came back online after being offline — reload to re-sync auth state
            window.location.reload();
          }
          return online;
        });
      } catch {
        if (!cancelled) setBackendOnline(false);
      }
    }
    checkHealth();
    const id = setInterval(checkHealth, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (retryAfter <= 0) return undefined;
    const timer = setInterval(() => {
      setRetryAfter((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAfter]);

  async function onPinSubmit(event) {
    event.preventDefault();
    const maxLength = isFirstRun ? 6 : 8;
    if (!new RegExp(`^\\d{4,${maxLength}}$`).test(pin)) {
      setError(isFirstRun ? 'Choose a PIN containing 4–6 digits.' : 'Enter your 4–8 digit PIN.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const fn = isFirstRun ? setPin : verifyPin;
      const data = await fn(pin);
      handleAuth(data.token);
    } catch (err) {
      if (err?.status === 429) {
        setRetryAfter(300);
        setError('Too many attempts. Unlocking will be available again shortly.');
      } else {
        setError(err?.message || (isFirstRun ? 'Failed to set PIN' : 'Incorrect PIN'));
      }
      setPinValue('');
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ fontFamily: "'Inter', sans-serif" }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-sm"
      >
        <div className="text-center mb-10">
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <h1 className="text-white/90 text-[2.2rem] tracking-[-0.06em]" style={{ fontWeight: 300 }}>GODFIN</h1>
            <p className="text-white/25 text-[0.65rem] tracking-[0.2em] uppercase">Personal Finance</p>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="relative overflow-hidden rounded-[24px] bg-white/[0.08] backdrop-blur-[32px] border border-white/[0.18] shadow-[0_16px_64px_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.2)] p-8"
        >
          <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent" />

          <div className="flex flex-col items-center mb-6 gap-2">
            <AnimatePresence mode="wait">
              {backendOnline ? (
                <motion.div
                  key="online"
                  initial={{ opacity: 0, scale: 0.8, rotate: -10 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.8, rotate: 10 }}
                  transition={{ duration: 0.3 }}
                  className="p-3 rounded-[18px] bg-emerald-400/[0.1] border border-emerald-400/[0.12]"
                >
                  <ShieldCheck className="h-8 w-8 text-emerald-400/70" />
                </motion.div>
              ) : (
                <motion.div
                  key="offline"
                  initial={{ opacity: 0, scale: 0.8, rotate: 10 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.8, rotate: -10 }}
                  transition={{ duration: 0.3 }}
                  className="p-3 rounded-[18px] bg-rose-400/[0.1] border border-rose-400/[0.12]"
                >
                  <ShieldAlert className="h-8 w-8 text-rose-400/70" />
                </motion.div>
              )}
            </AnimatePresence>
            <span className={`text-[0.6rem] tracking-[0.1em] uppercase transition-colors duration-300 ${backendOnline ? 'text-emerald-400/50' : 'text-rose-400/50'}`}>
              {backendOnline ? 'Backend Online' : 'Backend Offline'}
            </span>
          </div>

          <h2 className="text-white/80 text-[1.1rem] text-center mb-2" style={{ fontWeight: 400 }}>
            {isFirstRun ? 'Set Your PIN' : 'Enter Your PIN'}
          </h2>
          <p id="pin-length-hint" className="text-white/30 text-[0.8rem] text-center mb-8">
            {isFirstRun
              ? 'Choose 4–6 digits to secure your local data'
              : 'Enter your 4–6 digit PIN. Legacy 7–8 digit PINs still work.'}
          </p>

          <form onSubmit={onPinSubmit} className="space-y-4">
            <PinInput
              minLength={4}
              maxLength={isFirstRun ? 6 : 8}
              value={pin}
              onChange={setPinValue}
              autoSubmit={false}
              disabled={loading || retryAfter > 0 || !backendOnline}
              label={isFirstRun ? 'Choose a 4 to 6 digit PIN' : 'Enter your PIN'}
            />
            <button
              type="submit"
              disabled={loading || retryAfter > 0 || !backendOnline || pin.length < 4}
              className="w-full h-12 min-h-12 touch-manipulation rounded-[14px] bg-cyan-400/15 border border-cyan-300/20 text-cyan-100/80 text-[0.82rem] font-medium transition-colors hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? (isFirstRun ? 'Securing...' : 'Unlocking...') : (isFirstRun ? 'Set PIN' : 'Unlock')}
            </button>
          </form>

          {error && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-rose-400/80 text-[0.8rem] text-center mt-4">
              {error}
            </motion.p>
          )}

          {retryAfter > 0 && (
            <p className="text-amber-300/70 text-[0.75rem] text-center mt-3" role="status">
              Try again in {Math.floor(retryAfter / 60)}:{String(retryAfter % 60).padStart(2, '0')}
            </p>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
}
