import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import DialogSurface from './DialogSurface';

export function ConfirmDialog({ isOpen, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', onConfirm, onCancel, danger = false }) {
  const cancelRef = useRef(null);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            onClick={onCancel}
            data-godfin-dialog-backdrop="true"
            aria-hidden="true"
          />
          <DialogSurface
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            labelledBy="confirm-title"
            describedBy="confirm-description"
            initialFocusRef={cancelRef}
            onClose={onCancel}
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-sm bg-[#1a2a4a] border border-white/[0.12] rounded-[20px] shadow-2xl z-50 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-start justify-between mb-4">
                <h2 id="confirm-title" className="text-white/90 text-[1.1rem]" style={{ fontWeight: 500 }}>{title}</h2>
                <button
                  onClick={onCancel}
                  className="text-white/30 hover:text-white/60 transition-colors p-1"
                  aria-label="Close dialog"
                >
                  <X size={18} />
                </button>
              </div>
              <p id="confirm-description" className="text-white/50 text-[0.9rem] mb-6">{message}</p>
              <div className="flex gap-3 justify-end">
                <button
                  ref={cancelRef}
                  onClick={onCancel}
                  className="px-4 py-2 text-white/60 hover:text-white text-[0.85rem] transition-colors"
                >
                  {cancelLabel}
                </button>
                <button
                  onClick={onConfirm}
                  className={`px-4 py-2 rounded-[10px] text-white text-[0.85rem] transition-colors ${
                    danger
                      ? 'bg-rose-500/20 border border-rose-500/30 text-rose-400 hover:bg-rose-500/30'
                      : 'bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/30'
                  }`}
                >
                  {confirmLabel}
                </button>
              </div>
            </div>
          </DialogSurface>
        </>
      )}
    </AnimatePresence>
  );
}

export function useConfirm() {
  const [confirmState, setConfirmState] = useState({ isOpen: false, title: '', message: '', onConfirm: () => {} });

  const confirm = (options) => {
    return new Promise((resolve) => {
      setConfirmState({
        isOpen: true,
        title: options.title || 'Confirm',
        message: options.message || 'Are you sure?',
        confirmLabel: options.confirmLabel || 'Confirm',
        cancelLabel: options.cancelLabel || 'Cancel',
        danger: options.danger || false,
        onConfirm: () => {
          setConfirmState(prev => ({ ...prev, isOpen: false }));
          resolve(true);
        },
        onCancel: () => {
          setConfirmState(prev => ({ ...prev, isOpen: false }));
          resolve(false);
        },
      });
    });
  };

  return { confirm, ConfirmDialog: () => (
    <ConfirmDialog
      isOpen={confirmState.isOpen}
      title={confirmState.title}
      message={confirmState.message}
      confirmLabel={confirmState.confirmLabel}
      cancelLabel={confirmState.cancelLabel}
      danger={confirmState.danger}
      onConfirm={confirmState.onConfirm}
      onCancel={confirmState.onCancel}
    />
  )};
}
