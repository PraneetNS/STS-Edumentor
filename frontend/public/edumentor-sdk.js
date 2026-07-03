/**
 * EduMentor Voice Pipeline Client SDK
 * 
 * A high-performance, framework-agnostic JavaScript client for integrating
 * EduMentor's real-time voice, speech-to-text (Whisper), and text-to-speech (Kokoro) pipeline.
 * 
 * Version: 1.0.0
 * License: Apache-2.0
 */

export class EduMentorVoiceSDK {
  /**
   * Create an instance of the EduMentor Voice SDK
   * 
   * @param {Object} options
   * @param {string} options.wsUrl - The WebSocket endpoint (e.g. ws://127.0.0.1:8000/ws/voice)
   * @param {string} options.token - Valid JWT Access Token for authentication
   * @param {string} [options.sessionId] - Unique session identifier (defaults to random string)
   * @param {string} [options.voiceStyle="Friendly Mentor"] - Persona ("Friendly Mentor" | "Strict Evaluator" | "Fast Code Explainer")
   * @param {string} [options.accent="af_bella"] - Kokoro voice selector code (e.g. "af_bella", "am_adam", "bf_emma")
   * @param {number} [options.speechSpeed=1.0] - Speech speed multiplier (0.5 to 2.0)
   * @param {string} [options.audioProcessorUrl="/audio-processor.js"] - Path to the AudioWorklet processor file
   * @param {Function} [options.onStateChange] - Callback when connection/engine state updates
   * @param {Function} [options.onTranscript] - Callback for real-time speech-to-text transcripts
   * @param {Function} [options.onTextUpdate] - Callback for incoming LLM answer text streams
   * @param {Function} [options.onAudioPlaybackStart] - Callback when AI speaker begins speaking
   * @param {Function} [options.onAudioPlaybackEnd] - Callback when AI speaker stops speaking
   * @param {Function} [options.onInterrupt] - Callback when the AI speaker gets interrupted by user speech
   * @param {Function} [options.onError] - Callback for pipeline/connection errors
   */
  constructor(options = {}) {
    this.wsUrl = options.wsUrl || 'ws://127.0.0.1:8000/ws/voice';
    this.token = options.token || '';
    this.sessionId = options.sessionId || `sdk_${Math.random().toString(36).substring(2, 11)}`;
    this.voiceStyle = options.voiceStyle || 'Friendly Mentor';
    this.accent = options.accent || 'af_bella';
    this.speechSpeed = options.speechSpeed !== undefined ? options.speechSpeed : 1.0;
    this.audioProcessorUrl = options.audioProcessorUrl || '/audio-processor.js';

    // Callbacks
    this.onStateChange = options.onStateChange || (() => {});
    this.onTranscript = options.onTranscript || (() => {});
    this.onTextUpdate = options.onTextUpdate || (() => {});
    this.onAudioPlaybackStart = options.onAudioPlaybackStart || (() => {});
    this.onAudioPlaybackEnd = options.onAudioPlaybackEnd || (() => {});
    this.onInterrupt = options.onInterrupt || (() => {});
    this.onError = options.onError || (() => {});

    // Connection & Audio States
    this.ws = null;
    this.connectionState = 'disconnected'; // 'disconnected' | 'connecting' | 'connected' | 'error'
    this.isRecording = false;
    this.isProcessing = false;
    this.isPlaying = false;

    // Web Audio instances
    this.audioCtx = null;
    this.micStream = null;
    this.sourceNode = null;
    this.workletNode = null;
    this.analyser = null;
    this.micAnalyser = null;

    // Playback state variables
    this.playbackQueue = [];
    this.playbackState = 'idle'; // 'idle' | 'playing' | 'interrupting' | 'flushing'
    this.activeSource = null;
    this.nextPlayTime = 0;
    this.activeResponseId = null;
    this.activeTimeouts = [];
  }

  /**
   * Establish WebSocket connection to the EduMentor Voice backend
   * @returns {Promise<void>}
   */
  async connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this._setConnectionState('connecting');

    const url = new URL(this.wsUrl);
    url.searchParams.set('session_id', this.sessionId);
    url.searchParams.set('user_id', this.sessionId);
    url.searchParams.set('voice_style', this.voiceStyle);
    url.searchParams.set('accent', this.accent);
    url.searchParams.set('speech_speed', this.speechSpeed.toString());
    url.searchParams.set('token', this.token);

    this.ws = new WebSocket(url.toString());
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this._setConnectionState('connected');
      this._startPingInterval();
    };

    this.ws.onclose = (event) => {
      this._setConnectionState('disconnected');
      this._stopPingInterval();
      this.stopRecording();
      this._resetPlayback();
      if (event.code === 1008) {
        this.onError(new Error('Connection rejected: Authentication failed (1008).'));
      }
    };

    this.ws.onerror = (err) => {
      this._setConnectionState('error');
      this.onError(err);
    };

    this.ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        return;
      }

      try {
        const msg = JSON.parse(event.data);
        await this._handleServerMessage(msg);
      } catch (err) {
        this.onError(new Error(`Failed to parse WebSocket message: ${err.message}`));
      }
    };
  }

  /**
   * Disconnect WebSocket and release all microphones/audio context resources
   */
  disconnect() {
    this.stopRecording();
    this._resetPlayback();

    if (this.ws) {
      this.ws.close(1000, 'SDK request');
      this.ws = null;
    }
  }

  /**
   * Initialize browser audio context & AudioWorklet processor for microphone capture
   * @returns {Promise<AudioContext>}
   */
  async getAudioContext() {
    if (!this.audioCtx) {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioCtxClass({ sampleRate: 16000 });
      
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.connect(this.audioCtx.destination);

      this.micAnalyser = this.audioCtx.createAnalyser();
      this.micAnalyser.fftSize = 256;
    }

    if (this.audioCtx.state === 'suspended') {
      await this.audioCtx.resume();
    }
    return this.audioCtx;
  }

  /**
   * Start microphone recording and stream raw Int16 PCM frames over WebSocket
   * @returns {Promise<void>}
   */
  async startRecording() {
    if (this.isRecording) return;

    try {
      const ctx = await this.getAudioContext();
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        }
      });

      // Load AudioWorklet for Float32 to Int16 translation
      try {
        await ctx.audioWorklet.addModule(this.audioProcessorUrl);
      } catch (e) {
        throw new Error(`Failed to load AudioWorklet at ${this.audioProcessorUrl}: ${e.message}`);
      }

      this.sourceNode = ctx.createMediaStreamSource(this.micStream);
      this.workletNode = new AudioWorkletNode(ctx, 'audio-processor');

      this.sourceNode.connect(this.micAnalyser);
      this.sourceNode.connect(this.workletNode);
      this.workletNode.connect(ctx.destination);

      this.workletNode.port.onmessage = (event) => {
        const arrayBuffer = event.data;
        if (this.ws && this.ws.readyState === WebSocket.OPEN && this.isRecording) {
          this.ws.send(arrayBuffer);
        }
      };

      this.isRecording = true;
      this._emitState();
    } catch (err) {
      this.stopRecording();
      this.onError(err);
    }
  }

  /**
   * Stop microphone capturing
   */
  stopRecording() {
    if (!this.isRecording) return;

    try { this.sourceNode?.disconnect(); } catch (_) {}
    try { this.workletNode?.disconnect(); } catch (_) {}
    if (this.micStream) {
      this.micStream.getTracks().forEach(t => t.stop());
      this.micStream = null;
    }

    this.sourceNode = null;
    this.workletNode = null;
    this.isRecording = false;
    this._emitState();
  }

  /**
   * Update settings dynamically on the active connection
   * @param {Object} settings 
   */
  updateSettings(settings = {}) {
    if (settings.voiceStyle) this.voiceStyle = settings.voiceStyle;
    if (settings.accent) this.accent = settings.accent;
    if (settings.speechSpeed !== undefined) this.speechSpeed = settings.speechSpeed;

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'settings_update',
        settings: {
          voice_style: this.voiceStyle,
          accent: this.accent,
          speech_speed: this.speechSpeed
        }
      }));
    }
  }

  /**
   * Returns frequency data arrays for rendering waveforms/orbs
   */
  getAnalyserData() {
    const micData = new Uint8Array(this.micAnalyser ? this.micAnalyser.frequencyBinCount : 0);
    const speakerData = new Uint8Array(this.analyser ? this.analyser.frequencyBinCount : 0);

    if (this.micAnalyser) this.micAnalyser.getByteFrequencyData(micData);
    if (this.analyser) this.analyser.getByteFrequencyData(speakerData);

    return { micData, speakerData };
  }

  _setConnectionState(state) {
    this.connectionState = state;
    this._emitState();
  }

  _emitState() {
    this.onStateChange({
      connectionState: this.connectionState,
      isRecording: this.isRecording,
      isProcessing: this.isProcessing,
      isPlaying: this.isPlaying
    });
  }

  _startPingInterval() {
    this._stopPingInterval();
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 25000);
  }

  _stopPingInterval() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  async _handleServerMessage(msg) {
    switch (msg.type) {
      case 'transcript':
        this.onTranscript({
          text: msg.text,
          isFinal: msg.is_final
        });
        break;

      case 'text_delta':
        this.onTextUpdate({
          text: msg.text
        });
        break;

      case 'audio_chunk':
        if (msg.response_id && this.activeResponseId && msg.response_id !== this.activeResponseId) {
          return;
        }
        
        if (msg.audio) {
          const rawBuffer = this._base64ToArrayBuffer(msg.audio);
          const timestamps = msg.word_timestamps || [];
          await this._enqueueAudio(rawBuffer, timestamps, msg.response_id);
        }
        break;

      case 'playback_control':
        if (msg.action === 'interrupt') {
          this.activeResponseId = msg.response_id || null;
          this._resetPlayback();
          this.onInterrupt();
        } else if (msg.action === 'finished') {
          this.isProcessing = false;
          this._emitState();
        }
        break;

      case 'state_change':
        if (msg.state === 'THINKING') {
          this.isProcessing = true;
          this._emitState();
        } else if (msg.state === 'SPEAKING') {
          this.isProcessing = false;
          this._emitState();
        }
        break;
    }
  }

  _base64ToArrayBuffer(base64) {
    const binary = window.atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  _resetPlayback() {
    this.playbackState = 'interrupting';

    if (this.activeSource) {
      try { this.activeSource.stop(); } catch (_) {}
      this.activeSource = null;
    }

    this.playbackQueue = [];
    this.playbackState = 'flushing';
    this.isPlaying = false;
    this.nextPlayTime = 0;
    
    this.activeTimeouts.forEach(t => clearTimeout(t));
    this.activeTimeouts = [];

    this.playbackState = 'idle';
    this._emitState();
  }

  async _enqueueAudio(arrayBuffer, wordTimestamps, responseId) {
    if (this.playbackState === 'interrupting' || this.playbackState === 'flushing') {
      return;
    }

    try {
      const ctx = await this.getAudioContext();
      const decodedBuffer = await ctx.decodeAudioData(arrayBuffer);
      
      this.playbackQueue.push({
        audioBuffer: decodedBuffer,
        wordTimestamps,
        responseId
      });

      if (this.playbackState === 'idle') {
        this._drainPlaybackQueue();
      }
    } catch (err) {
      this.onError(new Error(`Failed to decode audio data: ${err.message}`));
    }
  }

  async _drainPlaybackQueue() {
    if (this.playbackQueue.length === 0 || this.playbackState === 'interrupting' || this.playbackState === 'flushing') {
      this.isPlaying = false;
      this.playbackState = 'idle';
      this._emitState();
      this.onAudioPlaybackEnd();
      return;
    }

    this.playbackState = 'playing';
    this.isPlaying = true;
    this._emitState();
    this.onAudioPlaybackStart();

    try {
      const ctx = await this.getAudioContext();
      const { audioBuffer, wordTimestamps, responseId } = this.playbackQueue.shift();

      if (responseId && this.activeResponseId && responseId !== this.activeResponseId) {
        this._drainPlaybackQueue();
        return;
      }

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.analyser);
      this.activeSource = source;

      const now = ctx.currentTime;
      let startTime = this.nextPlayTime;
      if (startTime < now) startTime = now;

      this.nextPlayTime = startTime + audioBuffer.duration;

      source.onended = () => {
        if (this.activeSource === source) this.activeSource = null;
        if (this.playbackState !== 'interrupting' && this.playbackState !== 'flushing') {
          this._drainPlaybackQueue();
        }
      };

      source.start(startTime);
    } catch (err) {
      this.onError(err);
      this.isPlaying = false;
      this.playbackState = 'idle';
      this._emitState();
    }
  }
}
