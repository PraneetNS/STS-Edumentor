import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

export function Dialog({
  isOpen,
  onClose,
  title,
  children,
  className = '',
}) {
  const overlayRef = useRef(null);

  // Close on Escape key press
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose();
    }
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      // Prevent body scrolling when open
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Overlay */}
          <motion.div
            ref={overlayRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-zinc-950/40 backdrop-blur-sm dark:bg-zinc-950/60"
            role="presentation"
          />

          {/* Dialog Body */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.3, type: 'spring', bounce: 0.15 }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            className={`relative z-10 w-full max-w-lg rounded-xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-800 dark:bg-zinc-900 ${className}`}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              {title && (
                <h2 id="dialog-title" className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
                  {title}
                </h2>
              )}
              <button
                onClick={onClose}
                aria-label="Close dialog"
                className="rounded-full p-1 text-zinc-400 hover:bg-zinc-150 dark:hover:bg-zinc-800 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="text-sm leading-relaxed text-zinc-650 dark:text-zinc-350">
              {children}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
