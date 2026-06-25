/**
 * useVoicePipeline — Custom React hook for the EduMentor Voice pipeline.
 *
 * Manages:
 *  - WebSocket connection to the FastAPI backend
 *  - Microphone capture via AudioContext + AudioWorklet
 *  - Streaming raw PCM Int16 audio to the backend
 *  - Receiving JSON events (transcript, text deltas, audio chunks with timestamps)
 *  - Dual AnalyserNodes: visualizing mic input without feedback vs speaker output
 *  - Word timing queues and timeout schedulers for speech text sync
 *  - Gapless sequential audio playback via a queued AudioBufferSourceNode chain
 */

import { useState, useRef, useCallback, useEffect } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/voice';
const SAMPLE_RATE = 16000; // Must match backend Config.AUDIO_SAMPLE_RATE

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
  // ── State ─────────────────────────────────────────────────────────────────
  const [isRecording, setIsRecording]     = useState(false);
  const [isProcessing, setIsProcessing]   = useState(false);
  const [isPlaying, setIsPlaying]         = useState(false);
  const [isInterrupted, setIsInterrupted] = useState(false);
  const [status, setStatus]               = useState('disconnected');
  const [transcript, setTranscript]       = useState('');
  const [assistantText, setAssistantText] = useState('');
  const [liveWords, setLiveWords]         = useState([]); // Word array with statuses
  const [currentSpokenWordIndex, setCurrentSpokenWordIndex] = useState(-1); // Active word index
  const [conversationState, setConversationState] = useState('IDLE');
  const [isSpeakingTextSync, setIsSpeakingTextSync] = useState(true);

  // ── Refs ──────────────────────────────────────────────────────────────────
  const currentTranscriptRef      = useRef('');
  const currentAssistantTextRef   = useRef('');
  const assistantCharsDeliveredRef = useRef(0);
  const clientSilenceTimerRef     = useRef(null);  // Client-side auto-stop timer
  const clientInactivityTimerRef  = useRef(null);  // Client-side absolute inactivity timer
  const hasSpeechRef              = useRef(false);  // True once live transcript arrives

  const onTranscriptRef = useRef(onTranscript);
  const onThinkingRef = useRef(onThinking);
  const onTextUpdateRef = useRef(onTextUpdate);
  const onFinishedRef = useRef(onFinished);
  const onInterruptRef = useRef(onInterrupt);

  // Decoupled streaming state
  const generatedTextBufferRef = useRef('');
  const fallbackToTokenStreamingRef = useRef(false);
  const hasReceivedAudioWithTimestampsRef = useRef(false);
  const retryCountRef = useRef(0);
  const isManualDisconnectRef = useRef(false);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onThinkingRef.current = onThinking;
    onTextUpdateRef.current = onTextUpdate;
    onFinishedRef.current = onFinished;
    onInterruptRef.current = onInterrupt;
  }, [onTranscript, onThinking, onTextUpdate, onFinished, onInterrupt]);

  const wsRef          = useRef(null);   // WebSocket
  const reconnectTimerRef = useRef(null); // Auto-reconnect timer
  const audioCtxRef    = useRef(null);   // AudioContext
  const workletNodeRef = useRef(null);   // AudioWorkletNode
  const streamRef      = useRef(null);   // MediaStream
  const sourceNodeRef  = useRef(null);   // MediaStreamSourceNode
  const workletLoadedRef = useRef(false); // Guard: addModule only once per AudioContext

  // Visualizer AnalyserNodes
  const analyserRef    = useRef(null);   // Playback analyser (destined to speakers)
  const micAnalyserRef = useRef(null);   // Mic analyser (isolated)
  const activeSourceRef = useRef(null);   // Currently playing source node ref

  // Audio playback queue
  const playbackQueueRef = useRef([]);     // Array<{ audioBuffer, wordTimestamps }>
  const isPlayingRef     = useRef(false);  // Stable playback flag
  const nextPlayTimeRef  = useRef(0);      // Scheduled play cursor (seconds)

  // Timestamps sync state
  const activeTimeoutsRef      = useRef([]); // Outstanding setTimeout IDs for highlights
  const totalEnqueuedWordsRef  = useRef(0);  // Total word count processed this turn
  const hasFinishedStreamingRef = useRef(false);

  // ── Timers Cleanup ────────────────────────────────────────────────────────
  const clearTimeouts = useCallback(() => {
    activeTimeoutsRef.current.forEach(t => clearTimeout(t));
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
    // Disconnect the audio graph nodes before stopping tracks
    try { sourceNodeRef.current?.disconnect(); } catch (_) {}
    try { workletNodeRef.current?.disconnect(); } catch (_) {}
    streamRef.current?.getTracks().forEach(t => t.stop());
    workletNodeRef.current = null;
    sourceNodeRef.current  = null;
    streamRef.current      = null;
  }, [clearClientSilenceTimer, clearClientInactivityTimer]);

  // ── WebSocket connection ──────────────────────────────────────────────────
  // Connect to the backend FastAPI WebSocket server. Handles automatic reconnections
  // with exponential backoff and cleanup on connection failure or disconnect.
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    isManualDisconnectRef.current = false;

    // Build WebSocket URL with persistent session query parameters for resuming
    const wsUrlObj = new URL(WS_URL);
    if (conversationId) {
      wsUrlObj.searchParams.set('session_id', conversationId);
      wsUrlObj.searchParams.set('user_id', conversationId);
    }

    console.log(`[WS] Connecting with session_id: ${conversationId}`);
    const ws = new WebSocket(wsUrlObj.toString());
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = (event) => {
      handleMessageRef.current(event);
    };

    ws.onopen = () => {
      console.log('[WS] Connected successfully.');
      setStatus('connected');
      retryCountRef.current = 0; // Reset retries on successful connection
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      ws._pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25_000);
    };

    ws.onclose = () => {
      clearInterval(ws._pingInterval);
      setIsRecording(false);
      setIsProcessing(false);
      cleanupMic();
      clearTimeouts();

      // If manual disconnect occurred (switching chat, logout), do not auto-reconnect
      if (isManualDisconnectRef.current) {
        console.log('[WS] Manual disconnect. Skipping auto-reconnect.');
        setStatus('disconnected');
        return;
      }

      // Calculate exponential backoff: delay starts at 1s, grows up to a maximum of 15s
      const delay = Math.min(15000, 1000 * Math.pow(1.5, retryCountRef.current));
      console.warn(`[WS] Connection dropped. Reconnecting in ${Math.round(delay)}ms (retry #${retryCountRef.current + 1})...`);
      setStatus(`disconnected: reconnecting in ${Math.round(delay / 1000)}s...`);

      if (!reconnectTimerRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
        retryCountRef.current += 1;
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] Error detected', err);
      setStatus('error');
      ws.close();
    };
  }, [clearTimeouts, cleanupMic, conversationId]);

  const disconnect = useCallback(() => {
    console.log('[WS] Disconnecting manually...');
    isManualDisconnectRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    clearTimeouts();
  }, [clearTimeouts]);

  // Auto-connect on mount and reconnect on conversationId changes
  useEffect(() => {
    retryCountRef.current = 0; // Reset retries for new conversation session
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  // ── Audio playback helpers ────────────────────────────────────────────────
  const resetPlayback = useCallback(() => {
    if (activeSourceRef.current) {
      try {
        activeSourceRef.current.stop();
      } catch (e) {
        // Ignore
      }
      activeSourceRef.current = null;
    }
    playbackQueueRef.current = [];
    isPlayingRef.current = false;
    nextPlayTimeRef.current = 0;
    setIsPlaying(false);
    clearTimeouts();
    hasFinishedStreamingRef.current = false;

    // Reset progressive sync state
    setIsSpeakingTextSync(true);
    fallbackToTokenStreamingRef.current = false;
    hasReceivedAudioWithTimestampsRef.current = false;
    generatedTextBufferRef.current = '';
  }, [clearTimeouts]);

  // Clear pipeline state and stop playback when changing conversation sessions
  useEffect(() => {
    setTranscript('');
    setLiveWords([]);
    setAssistantText('');
    setIsRecording(false);
    setIsProcessing(false);
    cleanupMic();
    resetPlayback();
  }, [conversationId, resetPlayback, cleanupMic]);

  // Lazily create / resume AudioContext
  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE,
      });

      // 1. Playback Analyser (sends to speakers)
      const analyser = audioCtxRef.current.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(audioCtxRef.current.destination);
      analyserRef.current = analyser;

      // 2. Mic Analyser (isolated, does NOT connect to destination to avoid feedback)
      const micAnalyser = audioCtxRef.current.createAnalyser();
      micAnalyser.fftSize = 256;
      micAnalyserRef.current = micAnalyser;
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  // Sequential playback loop
  const drainPlaybackQueue = useCallback(async () => {
    if (playbackQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);

      if (hasFinishedStreamingRef.current) {
        hasFinishedStreamingRef.current = false;
        // Perfect cleanup of visual state
        setIsSpeakingTextSync(false);
        setConversationState('IDLE');
        setStatus('connected');
        setIsProcessing(false);
        setIsRecording(false);
        cleanupMic();
        if (onFinishedRef.current) {
          onFinishedRef.current();
        }
      }
      return;
    }

    isPlayingRef.current = true;
    setIsPlaying(true);

    try {
      const ctx = await getAudioContext();
      const { audioBuffer, wordTimestamps } = playbackQueueRef.current.shift();

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;

      if (analyserRef.current) {
        source.connect(analyserRef.current);
      } else {
        source.connect(ctx.destination);
      }

      activeSourceRef.current = source;

      const now = ctx.currentTime;
      let startTime = nextPlayTimeRef.current;
      if (startTime < now) {
        startTime = now;
      }

      // Schedule highlight timings
      wordTimestamps.forEach((word) => {
        const delayMs = (startTime + word.start - ctx.currentTime) * 1000;
        const timeoutId = setTimeout(() => {
          setCurrentSpokenWordIndex(word.absoluteIndex);
          assistantCharsDeliveredRef.current += word.word.length + 1;
        }, Math.max(0, delayMs));
        activeTimeoutsRef.current.push(timeoutId);
      });

      const chunkDuration = audioBuffer.duration;
      nextPlayTimeRef.current = startTime + chunkDuration;

      source.onended = () => {
        if (activeSourceRef.current === source) {
          activeSourceRef.current = null;
        }
        if (isPlayingRef.current) {
          drainPlaybackQueue();
        }
      };

      source.start(startTime);
    } catch (e) {
      console.error('[Playback] Error in drainPlaybackQueue', e);
      isPlayingRef.current = false;
      setIsPlaying(false);
    }
  }, [getAudioContext, cleanupMic]);

  // Decode audio segment and enqueue it
  const enqueueAudio = useCallback(async (arrayBuffer, wordTimestamps) => {
    try {
      const ctx = await getAudioContext();
      // Decode WAV data
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      
      playbackQueueRef.current.push({ audioBuffer, wordTimestamps });
      
      if (!isPlayingRef.current) {
        drainPlaybackQueue();
      }
    } catch (e) {
      console.error('[Playback] Error enqueuing audio chunk', e);
    }
  }, [getAudioContext, drainPlaybackQueue]);

  // Handle incoming JSON messages from the backend
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
            if (onThinkingRef.current) {
              onThinkingRef.current();
            }
          }
          break;
        case 'live_transcript':
          setTranscript(msg.text);
          if (msg.words) {
            setLiveWords(msg.words);
          }
          // Client-side silence watchdog: reset 1.2s auto-stop timer on every live transcript
          if (msg.text && msg.text.trim()) {
            hasSpeechRef.current = true;
            clearClientInactivityTimer();
            clearClientSilenceTimer();
            clientSilenceTimerRef.current = setTimeout(() => {
              // Only auto-stop if still recording and not already processing
              if (streamRef.current) {
                console.log('[VAD] Client silence watchdog: auto-stopping mic after 1.2s of silence');
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
          if (msg.words) {
            setLiveWords(msg.words);
          }
          setIsProcessing(true);
          setStatus('processing');
          if (onTranscriptRef.current) {
            onTranscriptRef.current(msg.text);
          }
          break;
        case 'assistant_text_delta':
          generatedTextBufferRef.current += msg.text;
          setAssistantText(generatedTextBufferRef.current);
          if (fallbackToTokenStreamingRef.current) {
            setIsSpeakingTextSync(false);
          }
          if (onTextUpdateRef.current) {
            onTextUpdateRef.current(generatedTextBufferRef.current);
          }
          break;
        case 'audio_chunk':
          if (msg.audio) {
            const arrayBuffer = base64ToArrayBuffer(msg.audio);
            const rawTimestamps = msg.word_timestamps || [];
            
            if (rawTimestamps.length > 0) {
              hasReceivedAudioWithTimestampsRef.current = true;
            } else if (!hasReceivedAudioWithTimestampsRef.current) {
              // Trigger fallback to token streaming immediately if no timestamps are present
              fallbackToTokenStreamingRef.current = true;
              setIsSpeakingTextSync(false);
              if (onTextUpdateRef.current) {
                onTextUpdateRef.current(generatedTextBufferRef.current);
              }
            }
            
            // Map offsets to absolute offsets
            const absoluteWords = rawTimestamps.map((w) => ({
              ...w,
              absoluteIndex: totalEnqueuedWordsRef.current + w.index,
            }));
            totalEnqueuedWordsRef.current += rawTimestamps.length;
            
            enqueueAudio(arrayBuffer, absoluteWords);
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
              onTextUpdateRef.current(generatedTextBufferRef.current);
            }
          }
          // Only transition to IDLE if the audio queue has finished playing
          if (!isPlayingRef.current) {
            hasFinishedStreamingRef.current = false;
            setIsSpeakingTextSync(false);
            setConversationState('IDLE');
            setStatus('connected');
            setIsProcessing(false);
            setIsRecording(false);
            cleanupMic();
            if (onFinishedRef.current) {
              onFinishedRef.current();
            }
          }
          break;
        case 'interrupt':
          resetPlayback();
          setIsProcessing(false);
          setIsInterrupted(true);
          setStatus('interrupted');
          setAssistantText('');
          currentAssistantTextRef.current = '';
          if (onInterruptRef.current) {
            onInterruptRef.current();
          }
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
  }, [enqueueAudio, resetPlayback, cleanupMic]);

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

  // ── Recording controls ────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      setStatus('Reconnecting…');
      connect();
      await new Promise(resolve => setTimeout(resolve, 800));
    }

    // Interruption handling
    if (isPlaying || isProcessing) {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'interrupt',
          context: {
            chars_sent:    assistantCharsDeliveredRef.current,
            audio_playing: isPlaying,
          },
        }));
      }
      resetPlayback();
      setIsProcessing(false);
      setIsInterrupted(true);
      if (onInterruptRef.current) {
        onInterruptRef.current();
      }
    }

    // Reset states for new turn
    totalEnqueuedWordsRef.current = 0;
    hasSpeechRef.current = false;
    clearClientSilenceTimer();
    clearTimeouts();
    hasFinishedStreamingRef.current = false;

    // Reset progressive sync state
    setIsSpeakingTextSync(true);
    fallbackToTokenStreamingRef.current = false;
    hasReceivedAudioWithTimestampsRef.current = false;
    generatedTextBufferRef.current = '';

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
      streamRef.current = stream;

      const ctx = getAudioContext();

      // Load AudioWorklet module only once per AudioContext lifetime
      if (!workletLoadedRef.current) {
        await ctx.audioWorklet.addModule('/audio-processor.js');
        workletLoadedRef.current = true;
      }

      const sourceNode = ctx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(ctx, 'audio-processor');

      // Connect sourceNode to isolated mic analyser for canvas waveform
      if (micAnalyserRef.current) {
        sourceNode.connect(micAnalyserRef.current);
      }

      workletNode.port.onmessage = (event) => {
        // Only stream microphone data to the backend if the assistant is not currently speaking.
        // This prevents acoustic feedback/echo from triggering accidental barge-ins or muddying Whisper STT.
        if (wsRef.current?.readyState === WebSocket.OPEN && !isPlayingRef.current) {
          wsRef.current.send(event.data);
        }
      };

      // IMPORTANT: Do NOT connect workletNode to ctx.destination.
      // The worklet's only job is to forward PCM to the WebSocket.
      // Connecting it to destination would keep the audio hardware
      // active after cleanupMic(), causing the mic indicator to stay on.
      sourceNode.connect(workletNode);

      sourceNodeRef.current  = sourceNode;
      workletNodeRef.current = workletNode;

      setIsRecording(true);
      setTranscript('');
      setAssistantText('');
      setLiveWords([]);
      currentTranscriptRef.current = '';
      currentAssistantTextRef.current = '';
      assistantCharsDeliveredRef.current = 0;
      resetPlayback();
      setStatus('recording');

      // Start 5-second absolute inactivity watchdog to auto-close mic if no speech is detected
      clientInactivityTimerRef.current = setTimeout(() => {
        if (!hasSpeechRef.current) {
          console.log('[VAD] Client inactivity watchdog: no speech detected for 5s, stopping mic.');
          cleanupMic();
          setIsRecording(false);
          setStatus('connected');
        }
      }, 5000);
    } catch (err) {
      console.error('[Mic] error', err);
      setStatus('Mic access denied');
    }
  }, [connect, getAudioContext, isPlaying, isProcessing, resetPlayback, clearTimeouts, clearClientSilenceTimer, clearClientInactivityTimer, cleanupMic]);

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
          context: {
            chars_sent:    assistantCharsDeliveredRef.current,
            audio_playing: isPlaying,
          },
        }));
      }
      resetPlayback();
      cleanupMic();
      setIsRecording(false);
      setIsProcessing(false);
      setIsInterrupted(true);
      setStatus('connected');
      if (onInterruptRef.current) {
        onInterruptRef.current();
      }
    } else {
      if (isRecording) {
        stopRecording();
      } else {
        startRecording();
      }
    }
  }, [isRecording, isPlaying, isProcessing, startRecording, stopRecording, resetPlayback, cleanupMic]);

  // ── Public API ────────────────────────────────────────────────────────────
  return {
    isRecording,
    isProcessing,
    isPlaying,
    isInterrupted,
    status,
    transcript,
    assistantText,
    liveWords,                   // words with temporary/confirmed status
    currentSpokenWordIndex,      // absolute word index currently highlighted
    analyserNode: isRecording ? micAnalyserRef.current : analyserRef.current, // dynamic visualizer node
    conversationState,           // current state from backend
    isSpeakingTextSync,
    toggleRecording,
    connect,
    disconnect,
    sendWebSocketMessage,
  };
}
