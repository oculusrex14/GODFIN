import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ShieldCheck } from 'lucide-react';
import { changePin } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function ChangePinModal({ open, onClose }) {
  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const { handleAuth } = useAuth();

  function reset() {
    setCurrentPin('');
    setNewPin('');
    setConfirmPin('');
    setError('');
    setSuccess(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!/^\d{4,6}$/.test(newPin)) {
      setError('New PIN must be 4-6 digits');
      return;
    }
    if (newPin !== confirmPin) {
      setError('New PINs do not match');
      return;
    }
    if (currentPin === newPin) {
      setError('New PIN must be different from current');
      return;
    }

    setLoading(true);
    try {
      const data = await changePin(currentPin, newPin);
      handleAuth(data.token);
      setSuccess(true);
      setTimeout(handleClose, 1500);
    } catch (err) {
      setError(err.message || 'Failed to change PIN');
    } finally {
      setLoading(false);
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 z-50"
            onClick={handleClose}
          />
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed inset-x-4 bottom-4 top-auto sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-full sm:max-w-sm bg-slate-800 border border-slate-700 rounded-2xl z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
              <h2 className="text-base font-semibold text-white">Change PIN</h2>
              <button onClick={handleClose} className="text-slate-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>

            {success ? (
              <div className="p-8 text-center">
                <ShieldCheck className="h-10 w-10 text-emerald-400 mx-auto mb-3" />
                <p className="text-white font-medium">PIN Changed</p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="p-5 space-y-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Current PIN</label>
                  <input
                    type="password"
                    inputMode="numeric"
                    maxLength={8}
                    value={currentPin}
                    onChange={(e) => setCurrentPin(e.target.value.replace(/\D/g, ''))}
                    placeholder="Enter current PIN"
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none tabular-nums"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">New PIN</label>
                  <input
                    type="password"
                    inputMode="numeric"
                    maxLength={6}
                    value={newPin}
                    onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ''))}
                    placeholder="4-6 digits"
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none tabular-nums"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Confirm New PIN</label>
                  <input
                    type="password"
                    inputMode="numeric"
                    maxLength={6}
                    value={confirmPin}
                    onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ''))}
                    placeholder="Re-enter new PIN"
                    className="w-full bg-slate-700/50 border border-slate-600 rounded-lg text-sm text-white px-3 py-2 placeholder-slate-500 focus:border-emerald-400 focus:outline-none tabular-nums"
                  />
                </div>

                {error && <p className="text-rose-400 text-sm">{error}</p>}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-500/50 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {loading ? 'Changing...' : 'Change PIN'}
                </button>
              </form>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
