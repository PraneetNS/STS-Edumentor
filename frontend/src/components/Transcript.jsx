/**
 * Transcript — Live transcription bar shown at the bottom of the workspace.
 *
 * Shows the user's speech as it's being transcribed in real-time.
 * Animates new words appearing naturally.
 */
import React, { memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic } from 'lucide-react';

export const Transcript = memo(function Transcript({
  transcript,
  isRecording,
}) {
  const hasText = Boolean(transcript);
  const isActive = isRecording || hasText;

  return (
    <div className={`live-bar ${isActive ? 'active' : ''}`} aria-live="polite" aria-label="Live transcript">
      {/* Live indicator — only when recording */}
      <AnimatePresence>
        {isRecording && (
          <motion.div
            className="live-indicator"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{   opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.2 }}
          >
            <div className="live-dot" />
            <span className="live-label">Live</span>
          </motion.div>
        )}
        {!isRecording && !hasText && (
          <motion.div
            className="live-indicator"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.4 }}
          >
            <Mic size={12} style={{ color: 'var(--text-muted)' }} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Transcript text */}
      <div className={`live-text ${hasText ? 'has-text' : ''}`}>
        <AnimatePresence mode="wait">
          {hasText ? (
            <motion.span
              key="has-text"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{   opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              {transcript}
            </motion.span>
          ) : isRecording ? (
            <motion.span
              key="listening"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{   opacity: 0 }}
              style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}
            >
              Listening…
            </motion.span>
          ) : (
            <motion.span
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ color: 'var(--text-muted)' }}
            >
              Press the mic to start talking
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});
