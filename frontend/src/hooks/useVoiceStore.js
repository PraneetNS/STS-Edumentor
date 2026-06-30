import { useMemo } from 'react';
import { voiceStore } from '../stores/voiceStore';

export function useVoiceStore() {
  const connectionState = voiceStore.useStore((s) => s.connectionState);
  const conversationState = voiceStore.useStore((s) => s.conversationState);
  const isRecording = voiceStore.useStore((s) => s.isRecording);
  const isProcessing = voiceStore.useStore((s) => s.isProcessing);
  const isPlaying = voiceStore.useStore((s) => s.isPlaying);
  const micPermission = voiceStore.useStore((s) => s.micPermission);
  const isDuplicateTab = voiceStore.useStore((s) => s.isDuplicateTab);
  const liveWords = voiceStore.useStore((s) => s.liveWords);
  const currentSpokenWordIndex = voiceStore.useStore((s) => s.currentSpokenWordIndex);
  const status = voiceStore.useStore((s) => s.status);
  const liveTranscript = voiceStore.useStore((s) => s.liveTranscript);
  const amplitude = voiceStore.useStore((s) => s.amplitude);

  const actions = useMemo(() => ({
    setConnectionState: voiceStore.getState().setConnectionState,
    setConversationState: voiceStore.getState().setConversationState,
    setIsRecording: voiceStore.getState().setIsRecording,
    setIsProcessing: voiceStore.getState().setIsProcessing,
    setIsPlaying: voiceStore.getState().setIsPlaying,
    setMicPermission: voiceStore.getState().setMicPermission,
    setIsDuplicateTab: voiceStore.getState().setIsDuplicateTab,
    setLiveWords: voiceStore.getState().setLiveWords,
    setCurrentSpokenWordIndex: voiceStore.getState().setCurrentSpokenWordIndex,
    setStatus: voiceStore.getState().setStatus,
    setLiveTranscript: voiceStore.getState().setLiveTranscript,
    setAmplitude: voiceStore.getState().setAmplitude,
  }), []);

  return {
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
    liveTranscript,
    amplitude,
    ...actions,
  };
}
