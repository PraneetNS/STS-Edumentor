import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { PanelLeft } from 'lucide-react';

import { useVoicePipeline }       from './hooks/useVoicePipeline';
import { useConversationStore }   from './hooks/useConversationStore';
import { useToasts, ToastContainer } from './components/ToastContainer';

import { Sidebar }        from './components/Sidebar';
import { MessageList }    from './components/MessageList';
import { LiveTranscript } from './components/LiveTranscript';
import { VoiceOrb }       from './components/VoiceOrb';
import { ContextCards }   from './components/ContextCards';
import { EMOTIONS }       from './components/Avatar/AvatarAnimations';
import { MentorCharacter } from './components/MentorCharacter';

import './index.css';

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { toasts, addToast, removeToast } = useToasts();

  // ── Conversation state ──────────────────────────────────────────────────
  const {
    conversations,
    grouped,
    activeId,
    activeConversation,
    createConversation,
    selectConversation,
    deleteConversation,
    addMessage,
    updateStreamingMessage,
    setStreamingMessageText,
    finishStreamingMessage,
    saveMessageSnapshot,
  } = useConversationStore();

  const messages = activeConversation?.messages ?? [];

  // Active message ID ref to update the streaming assistant bubble in real-time
  const activeMsgIdRef = useRef(null);

  // Default static snapshot captured from the live mentor character
  const [defaultAvatarUrl, setDefaultAvatarUrl] = useState(null);

  // Optional: Extracted emotion from LLM (default to NORMAL if none)
  const [emotion, setEmotion] = useState(EMOTIONS.NORMAL);

  // ── Voice pipeline ──────────────────────────────────────────────────────
  const {
    isRecording,
    isProcessing,
    isPlaying,
    status,
    transcript,
    liveWords,
    currentSpokenWordIndex,
    analyserNode,
    conversationState,
    isSpeakingTextSync,
    toggleRecording,
  } = useVoicePipeline({
    conversationId: activeId,
    onTranscript: (text) => {
      addMessage('user', text);
    },
    onThinking: () => {
      const msgId = addMessage('assistant', '', { isStreaming: true });
      activeMsgIdRef.current = msgId;
      setEmotion(EMOTIONS.THINKING);
    },
    onTextUpdate: (fullText) => {
      if (activeMsgIdRef.current) {
        setStreamingMessageText(activeMsgIdRef.current, fullText);
      }
      if (fullText.includes('great') || fullText.includes('excellent')) setEmotion(EMOTIONS.ENCOURAGING);
      if (fullText.includes('!') && fullText.length > 50) setEmotion(EMOTIONS.EXCITED);
    },
    onFinished: () => {
      if (activeMsgIdRef.current) {
        finishStreamingMessage(activeMsgIdRef.current);
        activeMsgIdRef.current = null;
      }
      setEmotion(EMOTIONS.NORMAL);
    },
    onInterrupt: () => {
      if (activeMsgIdRef.current) {
        finishStreamingMessage(activeMsgIdRef.current);
        activeMsgIdRef.current = null;
      }
      setEmotion(EMOTIONS.NORMAL);
    }
  });

  // ── Error detection ─────────────────────────────────────────────────────
  const prevStatus = useRef(status);
  useEffect(() => {
    const prev = prevStatus.current;
    prevStatus.current = status;

    if (status === prev) return;

    if (status === 'disconnected' && prev !== 'connecting') {
      addToast('Connection lost. Please check the backend server.', 'warning');
      setEmotion(EMOTIONS.CONFUSED);
    }
    if (status?.startsWith('error:')) {
      addToast(`Pipeline error: ${status.replace('error: ', '')}`, 'error');
      setEmotion(EMOTIONS.CONFUSED);
    }
    if (status === 'Mic access denied') {
      addToast('Microphone access denied. Please allow mic access in your browser.', 'error');
    }
  }, [status, addToast]);

  // ── Keyboard shortcut: Space to toggle mic ──────────────────────────────
  useEffect(() => {
    function handleKey(e) {
      if (
        e.code === 'Space' &&
        !['INPUT', 'TEXTAREA', 'BUTTON'].includes(e.target.tagName) &&
        !isProcessing
      ) {
        e.preventDefault();
        toggleRecording();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [toggleRecording, isProcessing]);

  const isMintState = isRecording || isPlaying || conversationState === 'LISTENING' || conversationState === 'SPEAKING';
  const glowColor = isMintState ? '#10B981' : '#4F46E5';

  return (
    <>
      <div className="ambient-bg" aria-hidden="true">
        <div className="ambient-blob ambient-blob--1" />
        <div className="ambient-blob ambient-blob--2" />
        <div className="ambient-blob ambient-blob--3" />
      </div>

      <ToastContainer toasts={toasts} onDismiss={removeToast} />

      <motion.div
        className="app-shell"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6 }}
      >
        <Sidebar
          grouped={grouped}
          activeId={activeId}
          onSelect={selectConversation}
          onDelete={deleteConversation}
          onNewChat={createConversation}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <div className="workspace">
          {/* Header */}
          <header className="workspace-header">
            <div className="header-left">
              <button
                className="hamburger-btn"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
              >
                <PanelLeft size={18} />
              </button>
              <div className="header-logo">
                <div className="header-logo-icon">✦</div>
                <div>
                  <div className="header-title">
                    {activeConversation?.title === 'New Conversation' ? 'EduMentor' : activeConversation?.title ?? 'EduMentor'}
                  </div>
                  <div className="header-subtitle">AI Voice Tutor</div>
                </div>
              </div>
            </div>

            {/* Connection Status */}
            <div className="status-badge">
              <div className={`status-dot ${
                isRecording ? 'recording' :
                isProcessing ? 'processing' :
                isPlaying ? 'playing' :
                status === 'connected' ? 'connected' : ''
              }`} />
              {status === 'connected' ? (isRecording ? 'Listening' : isProcessing ? 'Thinking' : isPlaying ? 'Speaking' : 'Online') : 'Connecting...'}
            </div>
          </header>

          {/* MAIN SCROLL AREA */}
          <div className="flex-1 overflow-hidden flex flex-col relative z-10 pt-4">
            {messages.length === 0 && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="flex-1 flex flex-col items-center justify-center p-8 text-center"
                style={{ gap: '28px' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <div className="mentor-placeholder" />
                </div>
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '6px',
                }}>
                  <p style={{
                    fontSize: '18px',
                    fontWeight: '600',
                    color: 'var(--text-primary)',
                    letterSpacing: '-0.01em',
                    margin: 0,
                  }}>
                    Hey, I'm <span style={{ color: '#5457E5' }}>EDI</span>.
                  </p>
                  <p style={{
                    fontSize: '13px',
                    color: 'var(--text-muted)',
                    margin: 0,
                    lineHeight: '1.6',
                    maxWidth: '280px',
                  }}>
                    Press the mic below to start our session.
                  </p>
                </div>
              </motion.div>
            )}

            {/* Conversation Timeline */}
            <MessageList
              messages={messages}
              currentSpokenWordIndex={currentSpokenWordIndex}
              isSpeakingTextSync={isSpeakingTextSync}
              analyserNode={analyserNode}
              conversationState={conversationState}
              emotion={emotion}
              isPlaying={isPlaying}
              defaultAvatarUrl={defaultAvatarUrl}
              onSnapshot={saveMessageSnapshot}
            />
          </div>

          {/* VOICE INTERACTION ZONE (Fixed Bottom) */}
          <footer className="voice-zone">
            <div className="w-full max-w-2xl mx-auto flex flex-col gap-3">
              <div className="flex justify-center pb-1">
                <VoiceOrb
                  isRecording={isRecording}
                  isProcessing={isProcessing}
                  isPlaying={isPlaying}
                  conversationState={conversationState}
                  onClick={toggleRecording}
                />
              </div>
            </div>
          </footer>

          {/* Soft radial glow behind the 3D character */}
          <div 
            className={`mentor-glow ${messages.length > 0 ? 'chat-mode' : 'idle-mode'}`} 
            style={{ backgroundColor: glowColor }}
          />

          {/* Live 3D Mentor Character (Centered or Footer via CSS transition) */}
          <div className={`mentor-canvas-wrapper ${messages.length > 0 ? 'chat-mode' : 'idle-mode'}`}>
            <MentorCharacter
              state={
                isRecording ? 'listening' :
                isProcessing ? 'thinking' :
                isPlaying ? 'speaking' :
                'idle'
              }
              analyserNode={analyserNode}
              onSnapshot={!defaultAvatarUrl ? setDefaultAvatarUrl : undefined}
            />
          </div>
        </div>
      </motion.div>
    </>
  );
}
