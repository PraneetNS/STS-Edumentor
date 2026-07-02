/**
 * StatusBar — Connection and pipeline status pill.
 *
 * FIX 2: Extended to handle all connectionState values from useVoicePipeline:
 *   connecting    → gray dot, "Connecting…"
 *   connected     → green dot, "Online" (or active state label)
 *   reconnecting  → amber dot, "Reconnecting… (attempt N)"
 *   failed        → red dot, "Connection lost" + visible Reconnect button
 *   disconnected  → gray dot, "Disconnected"
 *
 * The 'failed' state shows a clickable Reconnect button calling manualReconnect()
 * so the student is never left stuck with no recovery path except page refresh.
 */
import React, { memo, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff, AlertCircle, RefreshCw } from 'lucide-react';

// Pipeline conversation-state → display label + dot style
const PIPELINE_STATE_MAP = {
  IDLE:         { label: 'Ready',       dotClass: 'connected'  },
  LISTENING:    { label: 'Listening',   dotClass: 'recording'  },
  TRANSCRIBING: { label: 'Transcribing…', dotClass: 'processing' },
  THINKING:     { label: 'Thinking…',   dotClass: 'processing' },
  SPEAKING:     { label: 'Speaking',    dotClass: 'playing'    },
  INTERRUPTED:  { label: 'Interrupted', dotClass: 'processing' },
  ERROR:        { label: 'Error',       dotClass: 'error', error: true },
};

/**
 * Derive display info from connection state + pipeline state.
 *
 * connectionState (FIX 2) takes priority over the fine-grained pipeline state
 * when the socket is not healthy.
 */
function getStatusInfo({
  connectionState,
  status,
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
  reconnectAttempt,
}) {
  // ── Connection-layer states (highest priority) ──────────────────────────
  if (connectionState === 'failed') {
    return {
      label:    'Connection lost',
      dotClass: 'error',
      icon:     WifiOff,
      error:    true,
      showReconnect: true,
    };
  }
  if (connectionState === 'reconnecting') {
    return {
      label:    `Reconnecting… (${reconnectAttempt ?? '…'})`,
      dotClass: 'processing',
      icon:     Wifi,
      error:    false,
      showReconnect: false,
    };
  }
  if (connectionState === 'connecting') {
    return {
      label:    'Connecting…',
      dotClass: 'processing',
      icon:     Wifi,
      error:    false,
      showReconnect: false,
    };
  }
  if (connectionState === 'disconnected') {
    return {
      label:    'Disconnected',
      dotClass: 'error',
      icon:     WifiOff,
      error:    true,
      showReconnect: false,
    };
  }

  // ── Legacy status string fallback ─────────────────────────────────────
  if (status === 'error' || status?.startsWith('error:') || conversationState === 'ERROR') {
    return { label: 'Error', dotClass: 'error', icon: AlertCircle, error: true, showReconnect: false };
  }

  // ── Connected: show pipeline state ────────────────────────────────────
  const stateInfo = PIPELINE_STATE_MAP[conversationState];
  if (stateInfo) return { ...stateInfo, icon: null, error: stateInfo.error || false, showReconnect: false };

  if (isRecording)  return { label: 'Recording', dotClass: 'recording',  icon: null, error: false, showReconnect: false };
  if (isProcessing) return { label: 'Thinking',  dotClass: 'processing', icon: null, error: false, showReconnect: false };
  if (isPlaying)    return { label: 'Speaking',  dotClass: 'playing',    icon: null, error: false, showReconnect: false };

  return { label: 'Online', dotClass: 'connected', icon: null, error: false, showReconnect: false };
}

export const StatusBar = memo(function StatusBar({
  connectionState = 'connected',
  status,
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
  manualReconnect,
  reconnectAttempt,
}) {
  const info = useMemo(
    () => getStatusInfo({
      connectionState,
      status,
      isRecording,
      isProcessing,
      isPlaying,
      conversationState,
      reconnectAttempt,
    }),
    [connectionState, status, isRecording, isProcessing, isPlaying, conversationState, reconnectAttempt],
  );

  return (
    <div
      className={`status-badge ${connectionState === 'connecting' || connectionState === 'reconnecting' ? 'connecting' : ''}`}
      aria-label={`Status: ${info.label}`}
      aria-live="polite"
      style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
    >
      {info.icon ? (
        <info.icon
          size={11}
          style={{ color: info.error ? 'var(--accent-red)' : 'var(--text-muted)', flexShrink: 0 }}
        />
      ) : (
        <div
          className={`status-dot ${info.dotClass}`}
          aria-hidden="true"
          style={info.dotClass === 'connected' ? {
            backgroundColor: '#22c55e',
            boxShadow: '0 0 0 2px rgba(34,197,94,0.25)',
          } : undefined}
        />
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

      {/* FIX 2 — Reconnect button shown only in 'failed' state */}
      {info.showReconnect && manualReconnect && (
        <button
          onClick={manualReconnect}
          aria-label="Reconnect"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            marginLeft: '6px',
            padding: '3px 10px',
            fontSize: '11px',
            fontWeight: '600',
            color: '#fff',
            background: 'var(--blue-500)',
            border: 'none',
            borderRadius: '999px',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <RefreshCw size={10} />
          Reconnect
        </button>
      )}
    </div>
  );
});
