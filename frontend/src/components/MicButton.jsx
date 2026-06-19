/**
 * MicButton — Premium voice control button.
 *
 * States: idle → recording → processing → speaking → idle
 *
 * When assistant is speaking, clicking interrupts it.
 * Animated ring pulse on recording.
 * Smooth state transitions via Framer Motion.
 */
import React, { memo, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, MicOff, Loader2, Volume2 } from 'lucide-react';

function getButtonState({ isRecording, isProcessing, isPlaying, conversationState }) {
  if (conversationState === 'LISTENING') return 'recording';
  if (conversationState === 'TRANSCRIBING' || conversationState === 'THINKING') return 'processing';
  if (conversationState === 'SPEAKING') return 'playing';

  if (isRecording)  return 'recording';
  if (isProcessing) return 'processing';
  if (isPlaying)    return 'playing';
  return 'idle';
}

const STATE_CONFIG = {
  idle: {
    label: 'Click to speak',
    sub:   'Ask a question',
    icon:  Mic,
    iconSize: 20,
    btnClass: 'idle',
    showRing: false,
  },
  recording: {
    label: 'Recording…',
    sub:   'Click to stop',
    icon:  MicOff,
    iconSize: 20,
    btnClass: 'recording',
    showRing: true,
  },
  processing: {
    label: 'Thinking…',
    sub:   'Please wait',
    icon:  Loader2,
    iconSize: 18,
    btnClass: 'processing',
    showRing: false,
  },
  playing: {
    label: 'EduMentor speaking',
    sub:   'Click to interrupt',
    icon:  Volume2,
    iconSize: 20,
    btnClass: 'playing',
    showRing: false,
  },
};

// Animated waveform bars shown when speaking
function Waveform({ active }) {
  if (!active) return null;
  return (
    <div className="waveform" style={{ color: 'var(--accent-cyan)' }}>
      {[0,1,2,3,4,5,6].map(i => (
        <motion.div
          key={i}
          className="waveform-bar"
          style={{ minHeight: 4, maxHeight: 20 }}
          animate={{ height: ['4px', `${8 + Math.random() * 12}px`, '4px'] }}
          transition={{
            duration: 0.5 + Math.random() * 0.3,
            repeat:   Infinity,
            ease:     'easeInOut',
            delay:    i * 0.07,
          }}
        />
      ))}
    </div>
  );
}

export const MicButton = memo(function MicButton({
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
  onClick,
}) {
  const stateKey = getButtonState({ isRecording, isProcessing, isPlaying, conversationState });
  const cfg      = STATE_CONFIG[stateKey];
  const Icon     = cfg.icon;

  const isDisabled = stateKey === 'processing';

  return (
    <div className="voice-controls" role="group" aria-label="Voice controls">
      {/* Mic button */}
      <div className="mic-btn-wrap">
        <motion.button
          className={`mic-btn ${cfg.btnClass}`}
          onClick={onClick}
          disabled={isDisabled}
          aria-label={cfg.label}
          aria-pressed={isRecording}
          whileHover={!isDisabled ? { scale: 1.08 } : {}}
          whileTap={!isDisabled   ? { scale: 0.94 } : {}}
          transition={{ type: 'spring', stiffness: 400, damping: 17 }}
          id="mic-button"
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={stateKey}
              initial={{ opacity: 0, scale: 0.7, rotate: -15 }}
              animate={{ opacity: 1, scale: 1,   rotate: 0 }}
              exit={{   opacity: 0, scale: 0.7, rotate: 15 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              <Icon size={cfg.iconSize} />
            </motion.div>
          </AnimatePresence>
        </motion.button>

        {/* Recording ring animation */}
        <AnimatePresence>
          {cfg.showRing && (
            <motion.div
              className="mic-ring"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{   opacity: 0 }}
            />
          )}
        </AnimatePresence>
      </div>

      {/* Status text */}
      <div className="voice-status">
        <AnimatePresence mode="wait">
          <motion.div
            key={stateKey}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{   opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            <div className="voice-status-line">{cfg.label}</div>
            <div className="voice-status-sub">{cfg.sub}</div>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Waveform (speaking state) */}
      <AnimatePresence>
        {isPlaying && (
          <motion.div
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{   opacity: 0, width: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Waveform active />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});
