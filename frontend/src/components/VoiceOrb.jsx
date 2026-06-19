/**
 * VoiceOrb — The large central primary interaction orb.
 *
 * States: idle | listening | thinking | speaking
 *
 * Uses Framer Motion for GPU-accelerated 60fps animations.
 * Completely redesigned to act as the main mic button in the bottom zone.
 */
import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Square } from 'lucide-react';

const ORB_CONFIGS = {
  idle: {
    gradient: ['#1e3a8a', '#4f46e5'],
    glow:     'rgba(79, 70, 229, 0.25)',
    label:    'Tap to talk',
    showMic:  true,
    showStop: false
  },
  listening: {
    gradient: ['#7c3aed', '#2563eb'],
    glow:     'rgba(124, 58, 237, 0.4)',
    label:    "I'm listening",
    showMic:  true,
    showStop: false
  },
  thinking: {
    gradient: ['#0ea5e9', '#6366f1'],
    glow:     'rgba(14, 165, 233, 0.3)',
    label:    'Thinking...',
    showMic:  false,
    showStop: false
  },
  speaking: {
    gradient: ['#059669', '#06b6d4'],
    glow:     'rgba(16, 185, 129, 0.3)',
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
        className="voice-orb-wrap" 
        onClick={onClick}
        role="button"
        aria-label={state === 'speaking' ? "Stop EDI" : "Toggle microphone"}
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      >
        <button className="voice-orb">
          {/* Background Glow */}
          <div 
            className="voice-orb-glow" 
            style={{ backgroundColor: cfg.glow, boxShadow: `0 0 60px ${cfg.glow}` }}
          />

          {/* Animated Rings for Listening */}
          {state === 'listening' && (
            <>
              <div className="voice-orb-ring" style={{ width: '80px', height: '80px', animationDelay: '0s' }} />
              <div className="voice-orb-ring" style={{ width: '80px', height: '80px', animationDelay: '0.8s' }} />
              <div className="voice-orb-ring" style={{ width: '80px', height: '80px', animationDelay: '1.6s' }} />
            </>
          )}

          {/* Core Button Area */}
          <div 
            className="voice-orb-core" 
            style={{ background: `linear-gradient(135deg, ${cfg.gradient[0]}, ${cfg.gradient[1]})` }}
          />

          {/* Spinner for Thinking */}
          {state === 'thinking' && <div className="voice-orb-spinner" />}

          {/* Content (Mic / Stop / Waveform) */}
          <div className="voice-orb-content">
            <AnimatePresence mode="wait">
              {cfg.showMic && (
                <motion.div
                  key="mic"
                  initial={{ opacity: 0, scale: 0.5 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.5 }}
                  transition={{ duration: 0.2 }}
                >
                  <Mic size={28} strokeWidth={2.5} />
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
                  <Square size={24} fill="currentColor" strokeWidth={0} />
                </motion.div>
              )}

              {state === 'speaking' && !cfg.showStop && (
                <motion.div
                  key="wave"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="orb-wave-bars"
                >
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="orb-wave-bar" style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
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
