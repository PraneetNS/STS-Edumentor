/**
 * VoiceOrb — The large central primary interaction orb.
 *
 * States: idle | listening | thinking | speaking
 *
 * Fully styled via index.css for premium white-mode border, shadow, and color overrides.
 */
import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Square } from 'lucide-react';

const ORB_CONFIGS = {
  idle: {
    label:    'Tap to talk',
    showMic:  true,
    showStop: false
  },
  listening: {
    label:    "I'm listening",
    showMic:  true,
    showStop: false
  },
  thinking: {
    label:    'Thinking...',
    showMic:  false,
    showStop: false
  },
  speaking: {
    label:    'Explaining',
    showMic:  false,
    showStop: true
  },
};

export const VoiceOrb = React.memo(function VoiceOrb({
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
  onClick
}) {
  const state = useMemo(() => {
    if (conversationState === 'LISTENING') return 'listening';
    if (conversationState === 'TRANSCRIBING' || conversationState === 'THINKING') return 'thinking';
    if (conversationState === 'SPEAKING') return 'speaking';

    if (isRecording)  return 'listening';
    if (isProcessing) return 'thinking';
    if (isPlaying)    return 'speaking';
    return 'idle';
  }, [conversationState, isRecording, isProcessing, isPlaying]);

  const cfg = ORB_CONFIGS[state];

  return (
    <div className="flex flex-col items-center gap-2">
      <div 
        className={`voice-orb-wrap state-${state}`} 
        onClick={onClick}
        role="button"
        aria-label={state === 'speaking' ? "Stop EDI" : "Toggle microphone"}
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      >
        <button className="voice-orb">
          {/* Animated Rings for Listening */}
          {state === 'listening' && (
            <>
              <div className="voice-orb-ring" style={{ width: '72px', height: '72px', animationDelay: '0s' }} />
              <div className="voice-orb-ring" style={{ width: '72px', height: '72px', animationDelay: '0.8s' }} />
              <div className="voice-orb-ring" style={{ width: '72px', height: '72px', animationDelay: '1.6s' }} />
            </>
          )}

          {/* Spinner for Thinking */}
          {state === 'thinking' && <div className="voice-orb-spinner" />}

          {/* Content (Mic / Stop / Waveform) */}
          <div className="voice-orb-content" style={{ color: 'currentColor' }}>
            <AnimatePresence mode="wait">
              {cfg.showMic && (
                <motion.div
                  key="mic"
                  initial={{ opacity: 0, scale: 0.5 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.5 }}
                  transition={{ duration: 0.2 }}
                >
                  <Mic size={24} strokeWidth={2.5} />
                </motion.div>
              )}
              
              {cfg.showStop && (
                <motion.div
                  key="stop"
                  initial={{ opacity: 0, scale: 0.5 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.5 }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-col items-center"
                >
                  <Square size={20} fill="currentColor" strokeWidth={0} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </button>
      </div>

      {/* Shortcut Hint */}
      {state === 'idle' && (
        <div className="voice-hint mt-1">
          <kbd>Space</kbd> to talk
        </div>
      )}
    </div>
  );
});
