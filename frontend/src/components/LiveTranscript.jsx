/**
 * LiveTranscript — Advanced user transcript rendering.
 *
 * Displays words word-by-word with visual states:
 *  - status: "temporary" (grey, italic, slightly transparent)
 *  - status: "confirmed" (white, opaque, pop-in animation)
 * Shows a subtle checkmark confirmation when speech correction finishes.
 */
import React, { memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, CheckCircle2 } from 'lucide-react';

export const LiveTranscript = memo(function LiveTranscript({
  transcript,
  liveWords = [],
  isRecording,
}) {
  const hasWords = liveWords && liveWords.length > 0;
  const hasText = isRecording && (hasWords || Boolean(transcript));
  const isActive = isRecording;

  // Check if transcript normalization is complete and successful
  const isFullyConfirmed = hasWords && liveWords.every(w => w.status === 'confirmed');

  return (
    <div className={`live-bar ${isActive ? 'active' : ''}`} aria-live="polite" aria-label="Live transcript">
      
      {/* Live Recording / Idle Indicator */}
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

      {/* Transcript Text Bubble */}
      <div className={`live-text ${hasText ? 'has-text' : ''}`}>
        <AnimatePresence mode="wait">
          {hasText ? (
            <motion.div
              key="has-text"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{   opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex flex-wrap gap-x-1.5 gap-y-0.5 justify-center items-center"
              style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '4px 6px', justifyContent: 'center' }}
            >
              {hasWords ? (
                liveWords.map((w, idx) => {
                  const isConfirmed = w.status === 'confirmed';
                  return (
                    <motion.span
                      key={`${idx}-${w.word}`}
                      initial={isConfirmed ? { opacity: 1, scale: 1 } : { opacity: 0.4, scale: 0.95 }}
                      animate={
                        isConfirmed
                          ? { opacity: 1, scale: 1, color: 'rgba(255, 255, 255, 0.95)' }
                          : { opacity: 0.55, scale: 1, color: 'rgba(255, 255, 255, 0.4)', fontStyle: 'italic' }
                      }
                      transition={{ duration: 0.24, ease: 'easeOut' }}
                      style={{ display: 'inline-block' }}
                    >
                      {w.word}
                    </motion.span>
                  );
                })
              ) : (
                <span>{transcript}</span>
              )}


            </motion.div>
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
