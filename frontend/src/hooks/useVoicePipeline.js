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

  const onTranscriptRef = useRef(onTranscript);
  const onThinkingRef = useRef(onThinking);
  const onTextUpdateRef = useRef(onTextUpdate);
  const onFinishedRef = useRef(onFinished);
  const onInterruptRef = useRef(onInterrupt);

  // Decoupled streaming state
  const generatedTextBufferRef = useRef('');
  const fallbackToTokenStreamingRef = useRef(false);
  const hasReceivedAudioWithTimestampsRef = useRef(false);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onThinkingRef.current = onThinking;
    onTextUpdateRef.current = onTextUpdate;
    onFinishedRef.current = onFinished;
    onInterruptRef.current = onInterrupt;
  }, [onTranscript, onThinking, onTextUpdate, onFinished, onInterrupt]);

  const wsRef          = useRef(null);   // WebSocket
  const audioCtxRef    = useRef(null);   // AudioContext
  const workletNodeRef = useRef(null);   // AudioWorkletNode
  const streamRef      = useRef(null);   // MediaStream
  const sourceNodeRef  = useRef(null);   // MediaStreamSourceNode

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

  const cleanupMic = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    workletNodeRef.current = null;
    sourceNodeRef.current  = null;
    streamRef.current      = null;
  }, []);

  // ── WebSocket connection ──────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = (event) => {
      handleMessageRef.current(event);
    };

    ws.onopen = () => {
      setStatus('connected');
      ws._pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25_000);
    };

    ws.onclose = () => {
      clearInterval(ws._pingInterval);
      setStatus('disconnected');
      setIsRecording(false);
      setIsProcessing(false);
      cleanupMic();
      clearTimeouts();
    };

    ws.onerror = (err) => {
      console.error('[WS] error', err);
      setStatus('error');
    };
  }, [clearTimeouts, cleanupMic]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    clearTimeouts();
  }, [clearTimeouts]);

  // Auto-connect on mount
  useEffect(() => {
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
      await ctx.audioWorklet.addModule('/audio-processor.js');

      const sourceNode = ctx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(ctx, 'audio-processor');

      // Connect sourceNode to isolated mic analyser for canvas waveform
      if (micAnalyserRef.current) {
        sourceNode.connect(micAnalyserRef.current);
      }

      workletNode.port.onmessage = (event) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data);
        }
      };

      sourceNode.connect(workletNode);
      workletNode.connect(ctx.destination);

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
    } catch (err) {
      console.error('[Mic] error', err);
      setStatus('Mic access denied');
    }
  }, [connect, getAudioContext, isPlaying, isProcessing, resetPlayback, clearTimeouts]);

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
