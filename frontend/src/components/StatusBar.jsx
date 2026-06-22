/**
 * StatusBar — Compact connection and pipeline status indicator.
 *
 * Shows: connection status, active pipeline state.
 * Designed as a small pill in the workspace header.
 */
import React, { memo, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff, AlertCircle } from 'lucide-react';

const STATE_MAP = {
  IDLE: { label: 'Ready', dotClass: 'connected' },
  LISTENING: { label: 'Listening', dotClass: 'recording' },
  TRANSCRIBING: { label: 'Transcribing…', dotClass: 'processing' },
  THINKING: { label: 'Thinking…', dotClass: 'processing' },
  SPEAKING: { label: 'Speaking', dotClass: 'playing' },
  INTERRUPTED: { label: 'Interrupted', dotClass: 'processing' },
  ERROR: { label: 'Error', dotClass: 'error', error: true }
};

function getStatusInfo(status, isRecording, isProcessing, isPlaying, conversationState) {
  if (status === 'error' || status?.startsWith('error:') || conversationState === 'ERROR') {
    return { label: 'Error', dotClass: 'error', icon: AlertCircle, error: true };
  }
  if (status === 'disconnected') {
    return { label: 'Disconnected', dotClass: 'error', icon: WifiOff, error: true };
  }
  if (status === 'connecting') {
    return { label: 'Connecting…', dotClass: 'processing', icon: Wifi, error: false };
  }

  const stateInfo = STATE_MAP[conversationState];
  if (stateInfo) {
    return { ...stateInfo, icon: null, error: stateInfo.error || false };
  }

  if (isRecording) {
    return { label: 'Recording', dotClass: 'recording', icon: null, error: false };
  }
  if (isProcessing) {
    return { label: 'Thinking', dotClass: 'processing', icon: null, error: false };
  }
  if (isPlaying) {
    return { label: 'Speaking', dotClass: 'playing', icon: null, error: false };
  }
  return { label: 'Ready', dotClass: 'connected', icon: null, error: false };
}

export const StatusBar = memo(function StatusBar({
  status,
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
}) {
  const info = useMemo(
    () => getStatusInfo(status, isRecording, isProcessing, isPlaying, conversationState),
    [status, isRecording, isProcessing, isPlaying, conversationState]
  );

  return (
    <div
      className={`status-badge ${status === 'connecting' ? 'connecting' : ''}`}
      aria-label={`Status: ${info.label}`}
      aria-live="polite"
    >
      {info.icon ? (
        <info.icon
          size={11}
          style={{ color: info.error ? 'var(--accent-red)' : 'var(--text-muted)', flexShrink: 0 }}
        />
      ) : (
        <div className={`status-dot ${info.dotClass}`} aria-hidden="true" />
      )}
      <AnimatePresence mode="wait">
        <motion.span
          key={info.label}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{   opacity: 0 }}
          transition={{ duration: 0.15 }}
          style={{ color: info.error ? 'var(--accent-red)' : undefined }}
        >
          {info.label}
        </motion.span>
      </AnimatePresence>
    </div>
  );
});
