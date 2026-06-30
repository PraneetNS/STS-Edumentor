import { createStore } from './createStore';

export const voiceStore = createStore((set) => ({
  connectionState: 'disconnected',
  conversationState: 'IDLE',
  isRecording: false,
  isProcessing: false,
  isPlaying: false,
  micPermission: 'prompt',
  isDuplicateTab: false,
  liveWords: [],
  currentSpokenWordIndex: -1,
  status: 'disconnected',
  liveTranscript: '',
  amplitude: 0,

  setConnectionState: (state) => set({ connectionState: state }),
  setConversationState: (state) => set({ conversationState: state }),
  setIsRecording: (recording) => set({ isRecording: recording }),
  setIsProcessing: (processing) => set({ isProcessing: processing }),
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  setMicPermission: (permission) => set({ micPermission: permission }),
  setIsDuplicateTab: (isDuplicate) => set({ isDuplicateTab: isDuplicate }),
  setLiveWords: (words) => set({ liveWords: words }),
  setCurrentSpokenWordIndex: (idx) => set({ currentSpokenWordIndex: idx }),
  setStatus: (status) => set({ status }),
  setLiveTranscript: (text) => set({ liveTranscript: text }),
  setAmplitude: (amp) => set({ amplitude: amp }),
}));
