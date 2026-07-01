/**
 * useVoicePipeline — Custom React hook for the EduMentor Voice pipeline.
 *
 * Resilience additions (production-grade):
 *  FIX 2 — Explicit reconnection state machine with exponential backoff.
 *           'connecting' | 'connected' | 'reconnecting' | 'failed' | 'disconnected'
 *           Exposes connectionState + manualReconnect for StatusBar.
 *  FIX 4 — Module-level singleton registry prevents duplicate WebSocket
 *           connections on React StrictMode double-invoke and remounts.
 *           Tab-level duplicate detection via BroadcastChannel (tabCoordination).
 *  FIX 3 — Mic permission state machine with Permissions API + onchange listener.
 *           Catches mid-session permission revocation without a page refresh.
 *  FIX 5 — Audio queue state machine with response_id discard of stale chunks.
 *           States: IDLE | PLAYING | INTERRUPTING | FLUSHING
 *
 * Original capabilities preserved:
 *  - WebSocket to FastAPI backend
 *  - Microphone capture via AudioContext + AudioWorklet
 *  - Streaming raw PCM Int16 to the backend
 *  - JSON event handling (transcript, text deltas, audio chunks with timestamps)
 *  - Dual AnalyserNodes: mic vs speaker, no feedback
 *  - Word timing queues and timeout schedulers for speech text sync
 *  - Gapless sequential audio playback via queued AudioBufferSourceNode chain
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { sanitizeAssistantText } from '../utils/sanitizeAssistantText';
import { registerSession, unregisterSession } from '../utils/tabCoordination';
import { voiceStore } from '../stores/voiceStore';
import { authStore } from '../stores/authStore';

// ── Constants ──────────────────────────────────────────────────────────────

const WS_URL        = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/voice';
const SAMPLE_RATE   = 16000; // Must match backend Config.AUDIO_SAMPLE_RATE

// FIX 2 — Reconnect parameters
const RECONNECT_BASE_DELAY    = 1000;
const RECONNECT_MAX_DELAY     = 16000;
const MAX_RECONNECT_ATTEMPTS  = 8;

// FIX 5 — Audio queue state machine values
const AudioQueueState = {
  IDLE:         'idle',
  PLAYING:      'playing',
  INTERRUPTING: 'interrupting',
  FLUSHING:     'flushing',
};

// ── FIX 4 — Module-level connection registry ───────────────────────────────
// Persists across component remounts and React StrictMode double-invocations.
// Key: sessionId → WebSocket instance
const activeConnections = new Map();

function getOrCreateConnection(sessionId, wsUrl) {
  const existing = activeConnections.get(sessionId);
  if (
    existing &&
    (existing.readyState === WebSocket.OPEN ||
      existing.readyState === WebSocket.CONNECTING)
  ) {
    return { ws: existing, reused: true };
  }
  // Stale entry — remove before creating fresh
  if (existing) activeConnections.delete(sessionId);

  const ws = new WebSocket(wsUrl);
  ws.binaryType = 'arraybuffer';
  activeConnections.set(sessionId, ws);
  return { ws, reused: false };
}

function releaseConnection(sessionId, ws) {
  const registered = activeConnections.get(sessionId);
  if (registered === ws) {
    activeConnections.delete(sessionId);
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function base64ToArrayBuffer(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

export function useVoicePipeline({
  onTranscript,
  onThinking,
  onTextUpdate,
  onFinished,
  onInterrupt,
  conversationId,
}) {
  // ── State ────────────────────────────────────────────────────────────────
  const [isRecording, setIsRecording]         = useState(false);
  const [isProcessing, setIsProcessing]       = useState(false);
  const [isPlaying, setIsPlaying]             = useState(false);
  const [isInterrupted, setIsInterrupted]     = useState(false);
  const [status, setStatus]                   = useState('disconnected');
  const [transcript, setTranscript]           = useState('');
  const [assistantText, setAssistantText]     = useState('');
  const [liveWords, setLiveWords]             = useState([]);
  const [currentSpokenWordIndex, setCurrentSpokenWordIndex] = useState(-1);
  const [conversationState, setConversationState] = useState('IDLE');
  const [isSpeakingTextSync, setIsSpeakingTextSync] = useState(true);

  // FIX 2 — Explicit connection state for StatusBar
  const [connectionState, setConnectionState] = useState('connecting');

  // FIX 3 — Mic permission state machine
  const [micPermission, setMicPermission] = useState('prompt');
  // 'prompt' | 'granted' | 'denied' | 'unsupported'

  // FIX 4 — Duplicate tab detection
  const [isDuplicateTab, setIsDuplicateTab] = useState(false);

  // ── Refs ─────────────────────────────────────────────────────────────────
  const currentTranscriptRef      = useRef('');
  const currentAssistantTextRef   = useRef('');
  const assistantCharsDeliveredRef = useRef(0);
  const clientSilenceTimerRef     = useRef(null);
  const clientInactivityTimerRef  = useRef(null);
  const hasSpeechRef              = useRef(false);

  const onTranscriptRef = useRef(onTranscript);
  const onThinkingRef   = useRef(onThinking);
  const onTextUpdateRef = useRef(onTextUpdate);
  const onFinishedRef   = useRef(onFinished);
  const onInterruptRef  = useRef(onInterrupt);

  // Decoupled streaming state
  const generatedTextBufferRef              = useRef('');
  const fallbackToTokenStreamingRef         = useRef(false);
  const hasReceivedAudioWithTimestampsRef   = useRef(false);

  // FIX 2 — Reconnect counters
  const reconnectAttemptsRef    = useRef(0);
  const reconnectTimeoutRef     = useRef(null);
  const isManualDisconnectRef   = useRef(false);

  // FIX 5 — Response ID for stale audio chunk discard
  const activeResponseIdRef   = useRef(null);
  const audioQueueStateRef    = useRef(AudioQueueState.IDLE);

  const wsRef           = useRef(null);
  const audioCtxRef     = useRef(null);
  const workletNodeRef  = useRef(null);
  const streamRef       = useRef(null);
  const sourceNodeRef   = useRef(null);
  const workletLoadedRef = useRef(false);

  const analyserRef     = useRef(null);
  const micAnalyserRef  = useRef(null);
  const activeSourceRef = useRef(null);

  const playbackQueueRef  = useRef([]);
  const isPlayingRef      = useRef(false);
  const nextPlayTimeRef   = useRef(0);
  const activeTimeoutsRef = useRef([]);
  const totalEnqueuedWordsRef    = useRef(0);
  const hasFinishedStreamingRef  = useRef(false);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onThinkingRef.current   = onThinking;
    onTextUpdateRef.current = onTextUpdate;
    onFinishedRef.current   = onFinished;
    onInterruptRef.current  = onInterrupt;
  }, [onTranscript, onThinking, onTextUpdate, onFinished, onInterrupt]);

  // ── FIX 3 — Mic permission state machine ──────────────────────────────────
  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicPermission('unsupported');
      return;
    }
    if (!navigator.permissions) return;

    navigator.permissions
      .query({ name: 'microphone' })
      .then((permissionStatus) => {
        setMicPermission(permissionStatus.state); // 'prompt' | 'granted' | 'denied'

        // Critical: fires when the user revokes permission mid-session via browser
        // chrome — catches the "silent failure" case without requiring a page refresh.
        permissionStatus.onchange = () => {
          setMicPermission(permissionStatus.state);
          if (permissionStatus.state === 'denied' && streamRef.current) {
            // Permission revoked while recording — stop immediately
            cleanupMic();
            setIsRecording(false);
            setStatus('connected');
          }
        };
      })
      .catch(() => {
        // Permissions API not supported in this browser — will fall back
        // to try/catch on actual getUserMedia call.
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── FIX 4 — Tab coordination ───────────────────────────────────────────
  useEffect(() => {
    if (!conversationId) return;
    registerSession(conversationId, () => {
      setIsDuplicateTab(true);
    });
    return () => unregisterSession();
  }, [conversationId]);

  // ── Timer helpers ──────────────────────────────────────────────────────
  const clearTimeouts = useCallback(() => {
    activeTimeoutsRef.current.forEach((t) => clearTimeout(t));
    activeTimeoutsRef.current = [];
    setCurrentSpokenWordIndex(-1);
  }, []);

  const clearClientSilenceTimer = useCallback(() => {
    if (clientSilenceTimerRef.current) {
      clearTimeout(clientSilenceTimerRef.current);
      clientSilenceTimerRef.current = null;
    }
  }, []);

  const clearClientInactivityTimer = useCallback(() => {
    if (clientInactivityTimerRef.current) {
      clearTimeout(clientInactivityTimerRef.current);
      clientInactivityTimerRef.current = null;
    }
  }, []);

  const cleanupMic = useCallback(() => {
    clearClientSilenceTimer();
    clearClientInactivityTimer();
    try { sourceNodeRef.current?.disconnect(); } catch (_) {}
    try { workletNodeRef.current?.disconnect(); } catch (_) {}
    streamRef.current?.getTracks().forEach((t) => t.stop());
    workletNodeRef.current = null;
    sourceNodeRef.current  = null;
    streamRef.current      = null;
  }, [clearClientSilenceTimer, clearClientInactivityTimer]);

  // ── FIX 2 — Reconnect with exponential backoff ────────────────────────
  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
      setConnectionState('failed');
      setStatus('Connection lost');
      return;
    }

    const attempt = reconnectAttemptsRef.current;
    setConnectionState('reconnecting');
    setStatus(`reconnecting:${attempt + 1}`);

    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, attempt),
      RECONNECT_MAX_DELAY,
    );
    reconnectAttemptsRef.current += 1;

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectTimeoutRef.current = null;
      connectWS(); // eslint-disable-line no-use-before-define
    }, delay);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── WebSocket connect ─────────────────────────────────────────────────
  const connectWS = useCallback(() => {
    // Guard: don't open a second socket if one is already live
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) return;

    setConnectionState('connecting');
    setStatus('connecting');
    isManualDisconnectRef.current = false;

    // Build URL with stable session_id so backend can resume context
    const wsUrlObj = new URL(WS_URL);
    if (conversationId) {
      wsUrlObj.searchParams.set('session_id', conversationId);
      wsUrlObj.searchParams.set('user_id', conversationId);
    }

    const token = authStore.getState().token;
    if (token) {
      wsUrlObj.searchParams.set('token', token);
    }

    // FIX 4 — reuse existing connection if one is already open for this session
    const { ws, reused } = getOrCreateConnection(
      conversationId || '_default',
      wsUrlObj.toString(),
    );
    wsRef.current = ws;

    if (reused) {
      // Socket is already open — just re-attach our handlers and mark connected
      setConnectionState('connected');
      setStatus('connected');
      reconnectAttemptsRef.current = 0;
      ws.onmessage = (event) => handleMessageRef.current(event);
      return;
    }

    ws.onmessage = (event) => handleMessageRef.current(event);

    ws.onopen = () => {
      setConnectionState('connected');
      setStatus('connected');
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      // Keep-alive ping every 25s
      ws._pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25_000);
    };

    ws.onclose = (event) => {
      clearInterval(ws._pingInterval);
      releaseConnection(conversationId || '_default', ws);
      setIsRecording(false);
      setIsProcessing(false);
      cleanupMic();
      clearTimeouts();

      if (isManualDisconnectRef.current) {
        // Normal closure (tab close, explicit disconnect) — no reconnect
        setConnectionState('disconnected');
        setStatus('disconnected');
        return;
      }

      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose fires after onerror — all reconnect logic lives there
      setStatus('error');
    };
  }, [conversationId, cleanupMic, clearTimeouts, scheduleReconnect]);

  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    wsRef.current?.close(1000, 'component unmounting');
    wsRef.current = null;
    clearTimeouts();
  }, [clearTimeouts]);

  // FIX 2 — Manual reconnect resets attempt counter before retrying
  const manualReconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    connectWS();
  }, [connectWS]);

  // Auto-connect on mount; disconnect on unmount
  useEffect(() => {
    reconnectAttemptsRef.current = 0;
    connectWS();
    return () => disconnect();
  }, [connectWS, disconnect]);

  // Reset pipeline when switching conversation sessions
  useEffect(() => {
    setTranscript('');
    setLiveWords([]);
    setAssistantText('');
    setIsRecording(false);
    setIsProcessing(false);
    cleanupMic();
  }, [conversationId, cleanupMic]);

  // ── Audio context ──────────────────────────────────────────────────────
  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE,
      });
      const analyser = audioCtxRef.current.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(audioCtxRef.current.destination);
      analyserRef.current = analyser;

      const micAnalyser = audioCtxRef.current.createAnalyser();
      micAnalyser.fftSize = 256;
      micAnalyserRef.current = micAnalyser;
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  // ── FIX 5 — Audio queue state machine ──────────────────────────────────
  // Explicit states prevent race conditions when barge-in and new TTS chunks
  // arrive simultaneously.

  const resetPlayback = useCallback(() => {
    audioQueueStateRef.current = AudioQueueState.INTERRUPTING;

    if (activeSourceRef.current) {
      try { activeSourceRef.current.pause?.(); } catch (_) {}
      try { activeSourceRef.current.stop(); }  catch (_) {}
      activeSourceRef.current = null;
    }

    playbackQueueRef.current = [];
    audioQueueStateRef.current = AudioQueueState.FLUSHING;

    isPlayingRef.current  = false;
    nextPlayTimeRef.current = 0;
    setIsPlaying(false);
    clearTimeouts();
    hasFinishedStreamingRef.current = false;

    setIsSpeakingTextSync(true);
    fallbackToTokenStreamingRef.current        = false;
    hasReceivedAudioWithTimestampsRef.current  = false;
    generatedTextBufferRef.current             = '';

    // Allow new audio to be enqueued immediately after flush
    audioQueueStateRef.current = AudioQueueState.IDLE;
  }, [clearTimeouts]);

  const drainPlaybackQueue = useCallback(async () => {
    if (
      playbackQueueRef.current.length === 0 ||
      audioQueueStateRef.current === AudioQueueState.INTERRUPTING ||
      audioQueueStateRef.current === AudioQueueState.FLUSHING
    ) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      audioQueueStateRef.current = AudioQueueState.IDLE;

      if (hasFinishedStreamingRef.current) {
        hasFinishedStreamingRef.current = false;
        setIsSpeakingTextSync(false);
        setConversationState('IDLE');
        setStatus('connected');
        setIsProcessing(false);
        setIsRecording(false);
        cleanupMic();
        if (onFinishedRef.current) onFinishedRef.current();
      }
      return;
    }

    audioQueueStateRef.current = AudioQueueState.PLAYING;
    isPlayingRef.current = true;
    setIsPlaying(true);

    try {
      const ctx = await getAudioContext();
      const { audioBuffer, wordTimestamps, responseId } = playbackQueueRef.current.shift();

      // FIX 5 — discard stale chunks from an interrupted response
      if (responseId && activeResponseIdRef.current && responseId !== activeResponseIdRef.current) {
        drainPlaybackQueue();
        return;
      }

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;

      if (analyserRef.current) {
        source.connect(analyserRef.current);
      } else {
        source.connect(ctx.destination);
      }
      activeSourceRef.current = source;

      const now       = ctx.currentTime;
      let startTime   = nextPlayTimeRef.current;
      if (startTime < now) startTime = now;

      wordTimestamps.forEach((word) => {
        const delayMs = (startTime + word.start - ctx.currentTime) * 1000;
        const tid = setTimeout(() => {
          setCurrentSpokenWordIndex(word.absoluteIndex);
          assistantCharsDeliveredRef.current += word.word.length + 1;
        }, Math.max(0, delayMs));
        activeTimeoutsRef.current.push(tid);
      });

      nextPlayTimeRef.current = startTime + audioBuffer.duration;

      source.onended = () => {
        if (activeSourceRef.current === source) activeSourceRef.current = null;
        if (
          audioQueueStateRef.current !== AudioQueueState.INTERRUPTING &&
          audioQueueStateRef.current !== AudioQueueState.FLUSHING
        ) {
          drainPlaybackQueue();
        }
      };

      source.start(startTime);
    } catch (e) {
      console.error('[Playback] Error in drainPlaybackQueue', e);
      isPlayingRef.current = false;
      setIsPlaying(false);
      audioQueueStateRef.current = AudioQueueState.IDLE;
    }
  }, [getAudioContext, cleanupMic]);

  const enqueueAudio = useCallback(async (arrayBuffer, wordTimestamps, responseId) => {
    // FIX 5 — drop chunks that belong to an already-interrupted response
    if (
      responseId &&
      activeResponseIdRef.current &&
      responseId !== activeResponseIdRef.current
    ) {
      return;
    }

    // Also drop if queue is being flushed right now
    if (
      audioQueueStateRef.current === AudioQueueState.INTERRUPTING ||
      audioQueueStateRef.current === AudioQueueState.FLUSHING
    ) {
      return;
    }

    try {
      const ctx    = await getAudioContext();
      const buffer = await ctx.decodeAudioData(arrayBuffer);
      playbackQueueRef.current.push({ audioBuffer: buffer, wordTimestamps, responseId });
      if (audioQueueStateRef.current === AudioQueueState.IDLE) {
        drainPlaybackQueue();
      }
    } catch (e) {
      console.error('[Playback] Error enqueuing audio chunk', e);
    }
  }, [getAudioContext, drainPlaybackQueue]);

  // ── WebSocket message handler ─────────────────────────────────────────
  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data);
      switch (msg.type) {

        case 'state':
          setConversationState(msg.state);
          if (msg.state === 'LISTENING' || msg.state === 'THINKING') {
            hasSpeechRef.current = true;
            clearClientInactivityTimer();
          }
          if (msg.state === 'THINKING') {
            setIsProcessing(true);
            setStatus('processing');
            if (onThinkingRef.current) onThinkingRef.current();
          }
          break;

        case 'live_transcript':
          setTranscript(msg.text);
          if (msg.words) setLiveWords(msg.words);
          if (msg.text?.trim()) {
            hasSpeechRef.current = true;
            clearClientInactivityTimer();
            clearClientSilenceTimer();
            clientSilenceTimerRef.current = setTimeout(() => {
              if (streamRef.current) {
                cleanupMic();
                setIsRecording(false);
                setIsProcessing(true);
                setStatus('processing');
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.send(JSON.stringify({ type: 'end_of_speech' }));
                }
              }
            }, 1200);
          }
          break;

        case 'transcript':
          setTranscript(msg.text);
          currentTranscriptRef.current = msg.text;
          if (msg.words) setLiveWords(msg.words);
          setIsProcessing(true);
          setStatus('processing');
          if (onTranscriptRef.current) onTranscriptRef.current(msg.text);
          // FIX 5 — assign a new response ID for this turn
          activeResponseIdRef.current = msg.response_id || crypto.randomUUID();
          break;

        case 'assistant_text_delta':
          generatedTextBufferRef.current += msg.text;
          {
            const displayText = sanitizeAssistantText(generatedTextBufferRef.current);
            setAssistantText(displayText);
            if (fallbackToTokenStreamingRef.current) setIsSpeakingTextSync(false);
            if (onTextUpdateRef.current) onTextUpdateRef.current(displayText);
          }
          break;

        case 'audio_chunk':
          if (msg.audio) {
            const arrayBuffer    = base64ToArrayBuffer(msg.audio);
            const rawTimestamps  = msg.word_timestamps || [];
            const chunkResponseId = msg.response_id || activeResponseIdRef.current;

            if (rawTimestamps.length > 0) {
              hasReceivedAudioWithTimestampsRef.current = true;
            } else if (!hasReceivedAudioWithTimestampsRef.current) {
              fallbackToTokenStreamingRef.current = true;
              setIsSpeakingTextSync(false);
              if (onTextUpdateRef.current) {
                onTextUpdateRef.current(sanitizeAssistantText(generatedTextBufferRef.current));
              }
            }

            const absoluteWords = rawTimestamps.map((w) => ({
              ...w,
              absoluteIndex: totalEnqueuedWordsRef.current + w.index,
            }));
            totalEnqueuedWordsRef.current += rawTimestamps.length;

            // FIX 5 — pass responseId so stale chunks can be discarded
            enqueueAudio(arrayBuffer, absoluteWords, chunkResponseId);
          }
          break;

        case 'tts_start':
          setIsPlaying(true);
          break;

        case 'vad_end_of_speech':
          clearClientSilenceTimer();
          cleanupMic();
          setIsRecording(false);
          setIsProcessing(true);
          setStatus('processing');
          break;

        case 'assistant_finished':
          hasFinishedStreamingRef.current = true;
          if (!hasReceivedAudioWithTimestampsRef.current) {
            fallbackToTokenStreamingRef.current = true;
            setIsSpeakingTextSync(false);
            if (onTextUpdateRef.current) {
              onTextUpdateRef.current(sanitizeAssistantText(generatedTextBufferRef.current));
            }
          }
          if (!isPlayingRef.current) {
            hasFinishedStreamingRef.current = false;
            setIsSpeakingTextSync(false);
            setConversationState('IDLE');
            setStatus('connected');
            setIsProcessing(false);
            setIsRecording(false);
            cleanupMic();
            if (onFinishedRef.current) onFinishedRef.current();
          }
          break;

        case 'interrupt':
          resetPlayback();
          setIsProcessing(false);
          setIsInterrupted(true);
          setStatus('interrupted');
          setAssistantText('');
          currentAssistantTextRef.current = '';
          if (onInterruptRef.current) onInterruptRef.current();
          break;

        case 'error':
          console.error('[Pipeline Error]', msg.text);
          setStatus(`error: ${msg.text}`);
          setIsProcessing(false);
          break;

        case 'pong':
          break;

        default:
          break;
      }
    } catch (e) {
      console.error('[WS] Failed to parse message JSON', e);
    }
  }, [enqueueAudio, resetPlayback, cleanupMic, clearClientSilenceTimer, clearClientInactivityTimer]);

  const handleMessageRef = useRef(handleMessage);
  useEffect(() => {
    handleMessageRef.current = handleMessage;
  }, [handleMessage]);

  const sendWebSocketMessage = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
      return true;
    }
    return false;
  }, []);

  // ── FIX 3 — Mic request with permission state update ──────────────────
  const requestMicStream = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      setMicPermission('granted');
      return stream;
    } catch (err) {
      setMicPermission('denied');
      return null;
    }
  }, []);

  // ── Recording controls ────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    // FIX 3 — block recording if permission denied or mic unsupported
    if (micPermission === 'denied' || micPermission === 'unsupported') {
      console.warn('[Mic] Cannot start recording — permission:', micPermission);
      return;
    }

    // FIX 4 — don't allow recording in duplicate tab
    if (isDuplicateTab) {
      console.warn('[Tab] Duplicate tab — recording blocked.');
      return;
    }

    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      setStatus('Reconnecting…');
      connectWS();
      await new Promise((resolve) => setTimeout(resolve, 800));
    }

    if (isPlaying || isProcessing) {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'interrupt',
          context: { chars_sent: assistantCharsDeliveredRef.current, audio_playing: isPlaying },
        }));
      }
      resetPlayback();
      setIsProcessing(false);
      setIsInterrupted(true);
      if (onInterruptRef.current) onInterruptRef.current();
    }

    // Reset per-turn state
    totalEnqueuedWordsRef.current             = 0;
    hasSpeechRef.current                      = false;
    hasFinishedStreamingRef.current           = false;
    fallbackToTokenStreamingRef.current       = false;
    hasReceivedAudioWithTimestampsRef.current = false;
    generatedTextBufferRef.current            = '';
    activeResponseIdRef.current               = null;
    clearClientSilenceTimer();
    clearTimeouts();
    setIsSpeakingTextSync(true);

    const stream = await requestMicStream();
    if (!stream) {
      setStatus('Mic access denied');
      return;
    }

    streamRef.current = stream;
    const ctx = getAudioContext();

    if (!workletLoadedRef.current) {
      await ctx.audioWorklet.addModule('/audio-processor.js');
      workletLoadedRef.current = true;
    }

    const sourceNode  = ctx.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(ctx, 'audio-processor');

    if (micAnalyserRef.current) sourceNode.connect(micAnalyserRef.current);

    workletNode.port.onmessage = (event) => {
      if (wsRef.current?.readyState === WebSocket.OPEN && !isPlayingRef.current) {
        wsRef.current.send(event.data);
      }
    };

    sourceNode.connect(workletNode);
    sourceNodeRef.current  = sourceNode;
    workletNodeRef.current = workletNode;

    setIsRecording(true);
    setTranscript('');
    setAssistantText('');
    setLiveWords([]);
    currentTranscriptRef.current        = '';
    currentAssistantTextRef.current     = '';
    assistantCharsDeliveredRef.current  = 0;
    resetPlayback();
    setStatus('recording');

    clientInactivityTimerRef.current = setTimeout(() => {
      if (!hasSpeechRef.current) {
        cleanupMic();
        setIsRecording(false);
        setStatus('connected');
      }
    }, 5000);
  }, [
    micPermission, isDuplicateTab, isPlaying, isProcessing,
    connectWS, getAudioContext, resetPlayback,
    clearTimeouts, clearClientSilenceTimer, cleanupMic, requestMicStream,
  ]);

  const stopRecording = useCallback(() => {
    cleanupMic();
    setIsRecording(false);
    setIsProcessing(true);
    setStatus('processing');
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_of_speech' }));
    }
  }, [cleanupMic]);

  const toggleRecording = useCallback(() => {
    if (isPlaying || isProcessing) {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'interrupt',
          context: { chars_sent: assistantCharsDeliveredRef.current, audio_playing: isPlaying },
        }));
      }
      resetPlayback();
      cleanupMic();
      setIsRecording(false);
      setIsProcessing(false);
      setIsInterrupted(true);
      setStatus('connected');
      if (onInterruptRef.current) onInterruptRef.current();
    } else {
      if (isRecording) stopRecording();
      else startRecording();
    }
  }, [isRecording, isPlaying, isProcessing, startRecording, stopRecording, resetPlayback, cleanupMic]);

  // Sync to global voiceStore to eliminate prop-drilling
  useEffect(() => {
    voiceStore.setState({
      connectionState,
      conversationState,
      isRecording,
      isProcessing,
      isPlaying,
      micPermission,
      isDuplicateTab,
      liveWords,
      currentSpokenWordIndex,
      status,
      liveTranscript: transcript,
    });
  }, [
    connectionState,
    conversationState,
    isRecording,
    isProcessing,
    isPlaying,
    micPermission,
    isDuplicateTab,
    liveWords,
    currentSpokenWordIndex,
    status,
    transcript
  ]);

  // ── Public API ────────────────────────────────────────────────────────
  return {
    // Pipeline state
    isRecording,
    isProcessing,
    isPlaying,
    isInterrupted,
    status,
    transcript,
    assistantText,
    liveWords,
    currentSpokenWordIndex,
    analyserNode: isRecording ? micAnalyserRef.current : analyserRef.current,
    conversationState,
    isSpeakingTextSync,
    // FIX 2 — connection state + manual reconnect
    connectionState,
    manualReconnect,
    // FIX 3 — mic permission
    micPermission,
    // FIX 4 — duplicate tab flag
    isDuplicateTab,
    // Actions
    toggleRecording,
    connect: connectWS,
    disconnect,
    sendWebSocketMessage,
  };
}
