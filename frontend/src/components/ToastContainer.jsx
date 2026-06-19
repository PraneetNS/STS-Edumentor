/**
 * ToastContainer — Beautiful non-blocking toast notifications.
 *
 * Replaces browser alert() for error states.
 * Auto-dismisses after 4 seconds.
 */
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

// ── Toast manager hook (exported for use in App) ───────────────────────────

export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const counterRef = useRef(0);

  const addToast = useCallback((message, type = 'error') => {
    const id = ++counterRef.current;
    setToasts(prev => [...prev, { id, message, type }]);
    return id;
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}

// ── Individual Toast ───────────────────────────────────────────────────────

const ICONS = {
  error:   AlertCircle,
  warning: AlertTriangle,
  info:    Info,
};

function Toast({ toast, onDismiss }) {
  const Icon = ICONS[toast.type] || Info;

  // Auto-dismiss
  useEffect(() => {
    const t = setTimeout(() => onDismiss(toast.id), 4000);
    return () => clearTimeout(t);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      className={`toast ${toast.type}`}
      initial={{ opacity: 0, x: 60, scale: 0.95 }}
      animate={{ opacity: 1, x: 0,  scale: 1 }}
      exit={{   opacity: 0, x: 60,  scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      role="alert"
      aria-live="assertive"
    >
      <Icon size={14} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'inherit', opacity: 0.6, padding: '2px', flexShrink: 0,
          display: 'flex', alignItems: 'center',
        }}
      >
        <X size={13} />
      </button>
    </motion.div>
  );
}

// ── Container ──────────────────────────────────────────────────────────────

export function ToastContainer({ toasts, onDismiss }) {
  return (
    <div className="toast-container" aria-label="Notifications">
      <AnimatePresence>
        {toasts.map(t => (
          <Toast key={t.id} toast={t} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}
