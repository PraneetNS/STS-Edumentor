import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { PanelLeft, Home, X, BookOpen, ExternalLink, FileText, Terminal, Download } from 'lucide-react';

import { useVoicePipeline } from './hooks/useVoicePipeline';
import { useConversationStore } from './hooks/useConversationStore';
import { useToasts, ToastContainer } from './components/ToastContainer';

import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { LiveTranscript } from './components/LiveTranscript';
import { VoiceOrb } from './components/VoiceOrb';
import { ContextCards } from './components/ContextCards';
import { MentorCharacter } from './components/MentorCharacter';
import ErrorBoundary from './components/ErrorBoundary';

import './styles/index.css';

import { MarkdownViewer } from './components/MarkdownViewer';
import { StatusBar } from './components/StatusBar';
import { authStore } from './stores/authStore';
import { LoginRegister } from './components/LoginRegister';
import { Profile } from './components/Profile';
import { SettingsView } from './components/SettingsView';
import { AnalyticsOverview } from './components/AnalyticsOverview';
import { User as UserIcon, LogOut, LayoutDashboard, Settings } from 'lucide-react';
import readmeContentRaw from '../../README.md?raw';

function trimToLastCompleteSentence(text) {
  if (!text) return '';
  
  // Keep completed show blocks intact, only cleaning up trailing content after them
  const lastShowClose = text.lastIndexOf('</show>');
  const lastCurlyShowClose = text.lastIndexOf('{/show}');
  const showCloseIndex = Math.max(lastShowClose, lastCurlyShowClose);
  
  if (showCloseIndex !== -1) {
    const showCloseLength = lastShowClose > lastCurlyShowClose ? 7 : 8;
    const showPart = text.substring(0, showCloseIndex + showCloseLength);
    const afterShow = text.substring(showCloseIndex + showCloseLength);
    const cleanedAfterShow = trimToLastCompleteSentence(afterShow);
    return showPart + cleanedAfterShow;
  }
  
  // Find the last index of sentence-ending punctuation (. or ! or ?)
  const lastIndex = Math.max(
    text.lastIndexOf('.'),
    text.lastIndexOf('!'),
    text.lastIndexOf('?')
  );
  
  if (lastIndex !== -1) {
    return text.substring(0, lastIndex + 1);
  }
  
  // Fallback: trim to the last complete word
  const trimmedText = text.trim();
  const lastSpaceIndex = trimmedText.lastIndexOf(' ');
  if (lastSpaceIndex !== -1) {
    return trimmedText.substring(0, lastSpaceIndex);
  }
  
  return text;
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { toasts, addToast, removeToast } = useToasts();
  const [view, setView] = useState('landing');
  const [showDocs, setShowDocs] = useState(false);
  const [readmeContent, setReadmeContent] = useState(readmeContentRaw);
  const [isLoadingReadme, setIsLoadingReadme] = useState(false);

  // Authentication & Dropdown State
  const user = authStore.useStore(s => s.user);
  const isAuthenticated = authStore.useStore(s => s.isAuthenticated);
  const isLoadingAuth = authStore.useStore(s => s.isLoading);
  const checkAuth = authStore.getState().checkAuth;
  const logout = authStore.getState().logout;
  const [avatarDropdownOpen, setAvatarDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setAvatarDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (urlToken) {
      try {
        const jwtPayload = JSON.parse(atob(urlToken.split('.')[1]));
        authStore.setState({
          token: urlToken,
          user: {
            user_id: jwtPayload.user_id,
            email: jwtPayload.email,
            display_name: jwtPayload.email.split('@')[0],
            avatar_url: null
          },
          isAuthenticated: true,
          isLoading: false
        });
        window.history.replaceState({}, document.title, '/');
      } catch (e) {
        console.error("Failed to decode SSO callback token:", e);
        checkAuth();
      }
    } else {
      checkAuth();
    }
  }, []);

  const [shortcutsEnabled, setShortcutsEnabled] = useState(() => {
    const saved = localStorage.getItem('shortcutsEnabled');
    return saved !== null ? JSON.parse(saved) : true;
  });

  useEffect(() => {
    localStorage.setItem('shortcutsEnabled', JSON.stringify(shortcutsEnabled));
  }, [shortcutsEnabled]);

  const launcherMessages = [
    '💬 Talk to an AI Mentor',
    "👋 Hey! I'm Edi",
    '🚀 Master engineering concepts',
    '🎙️ Ask me a question!'
  ];
  const [activeMessageIdx, setActiveMessageIdx] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveMessageIdx((prev) => (prev + 1) % launcherMessages.length);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  const disciplines = [
    {
      title: 'Computer Science',
      desc: 'Data structures, algorithms, system architecture, database design, and programming languages.',
      icon: '💻',
      color: 'linear-gradient(135deg, #3b82f6, #1d4ed8)'
    },
    {
      title: 'Mechanical Engineering',
      desc: 'Thermodynamics, fluid mechanics, stress analysis, mechanics of materials, and CAD designing.',
      icon: '⚙️',
      color: 'linear-gradient(135deg, #ef4444, #b91c1c)'
    },
    {
      title: 'Electrical Engineering',
      desc: 'Circuit analysis, microprocessors, signals & systems, electromagnetics, and control theory.',
      icon: '⚡',
      color: 'linear-gradient(135deg, #eab308, #a16207)'
    },
    {
      title: 'Civil Engineering',
      desc: 'Structural engineering, geotechnical mechanics, concrete designs, and fluid dynamics.',
      icon: '🏗️',
      color: 'linear-gradient(135deg, #10b981, #047857)'
    },
    {
      title: 'Chemical Engineering',
      desc: 'Reaction kinetics, thermodynamics, mass transport, heat transfer, and process control.',
      icon: '🧪',
      color: 'linear-gradient(135deg, #a855f7, #6b21a8)'
    },
    {
      title: 'Aerospace Engineering',
      desc: 'Aerodynamics, orbital mechanics, propulsion systems, flight stability, and structural design.',
      icon: '🚀',
      color: 'linear-gradient(135deg, #ec4899, #be185d)'
    }
  ];

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
    setStreamingMessageFollowup,
    finishStreamingMessage,
    saveMessageSnapshot,
  } = useConversationStore();

  useEffect(() => {
    if (isAuthenticated && activeConversation) {
      document.title = activeConversation.title === 'New Conversation'
        ? 'EduMentor Voice — AI Tutor'
        : `EduMentor — ${activeConversation.title}`;
    } else {
      document.title = 'EduMentor Voice — AI Tutor';
    }
  }, [isAuthenticated, activeConversation, activeConversation?.title]);

  const messages = activeConversation?.messages ?? [];

  // Active message ID ref to update the streaming assistant bubble in real-time
  const activeMsgIdRef = useRef(null);

  // FIX 1 — Reset callback passed to the MessageList ErrorBoundary.
  // Finalises any stuck streaming bubble so state is clean after recovery.
  const resetMessageListRef = useRef(null);
  const resetMessageList = useCallback(() => {
    if (activeMsgIdRef.current) {
      finishStreamingMessage(activeMsgIdRef.current);
      activeMsgIdRef.current = null;
    }
  }, [finishStreamingMessage]);
  resetMessageListRef.current = resetMessageList;

  // Default static snapshot captured from the live mentor character
  const [defaultAvatarUrl, setDefaultAvatarUrl] = useState(null);

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
    // FIX 2 — connection state machine
    connectionState,
    manualReconnect,
    // FIX 3 — mic permission
    micPermission,
    // FIX 4 — duplicate tab
    isDuplicateTab,
  } = useVoicePipeline({
    conversationId: activeId,
    onTranscript: (text) => {
      // Guard: never add an empty user bubble — happens when STT
      // produces nothing (silence, noise, too short). The backend
      // will handle the "didn't hear you" response separately.
      if (!text || !text.trim()) return;
      addMessage('user', text);
    },
    onThinking: () => {
      const msgId = addMessage('assistant', '', { isStreaming: true });
      activeMsgIdRef.current = msgId;
    },
    onTextUpdate: (fullText) => {
      if (activeMsgIdRef.current) {
        setStreamingMessageText(activeMsgIdRef.current, fullText);
      }
    },
    onFinished: () => {
      if (activeMsgIdRef.current) {
        finishStreamingMessage(activeMsgIdRef.current);
        activeMsgIdRef.current = null;
      }
    },
    onInterrupt: () => {
      if (activeMsgIdRef.current) {
        const activeMsg = activeConversation?.messages.find(m => m.id === activeMsgIdRef.current);
        if (activeMsg && activeMsg.text) {
          const cleanedText = trimToLastCompleteSentence(activeMsg.text);
          setStreamingMessageText(activeMsgIdRef.current, cleanedText);
        }
        finishStreamingMessage(activeMsgIdRef.current);
        activeMsgIdRef.current = null;
      }
    }
  });

  // README loaded statically at build time.

  // ── Error detection ─────────────────────────────────────────────────────
  const prevStatus = useRef(status);
  useEffect(() => {
    const prev = prevStatus.current;
    prevStatus.current = status;

    if (status === prev) return;

    if (status === 'disconnected' && prev !== 'connecting') {
      addToast('Connection lost. Please check the backend server.', 'warning');
    }
    if (status?.startsWith('error:')) {
      addToast(`Pipeline error: ${status.replace('error: ', '')}`, 'error');
    }
    if (status === 'Mic access denied') {
      addToast('Microphone access denied. Please allow mic access in your browser.', 'error');
    }
  }, [status, addToast]);

  // ── Keyboard shortcut: Space to toggle mic ──────────────────────────────
  useEffect(() => {
    function handleKey(e) {
      if (!shortcutsEnabled) return;
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
  }, [toggleRecording, isProcessing, shortcutsEnabled]);

  const lastAssistantMessage = messages.slice().reverse().find((m) => m.role === 'assistant');
  const isMintState = isRecording || isPlaying || conversationState === 'LISTENING' || conversationState === 'SPEAKING';
  const glowColor = isMintState ? '#10B981' : '#4F46E5';

  if (isLoadingAuth) {
    return (
      <div className="w-screen h-screen bg-[#0A0B0E] flex flex-col items-center justify-center text-slate-400 gap-4 font-mono">
        <div className="w-10 h-10 border-4 border-slate-800 border-t-orange-500 rounded-full animate-spin" />
        <div className="text-[10px] uppercase tracking-widest text-slate-500">INITIALIZING SECURITY SYSTEM...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <ToastContainer toasts={toasts} onDismiss={removeToast} />
        <LoginRegister />
      </>
    );
  }

  return (
    <>
      <div className="ambient-bg" aria-hidden="true">
        <div className="ambient-blob ambient-blob--1" />
        <div className="ambient-blob ambient-blob--2" />
        <div className="ambient-blob ambient-blob--3" />
      </div>

      <ToastContainer toasts={toasts} onDismiss={removeToast} />

      {view === 'landing' ? (
        <div className="landing-container">
          {/* Navigation Bar */}
          <nav className="landing-nav">
            <div className="header-logo">
              <div className="header-logo-icon" style={{ background: 'transparent', boxShadow: 'none', padding: 0 }}>
                <img src="/mascot.png" alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain', mixBlendMode: 'multiply' }} />
              </div>
              <div>
                <div className="header-title">EduMentor</div>
                <div className="header-subtitle">AI Engineering Mentor</div>
              </div>
            </div>
            <div className="landing-nav-links">
              <a href="#features" className="landing-nav-link">Disciplines</a>
              <a href="#sdk" className="landing-nav-link">SDK Integration</a>
              <a href="#docs" className="landing-nav-link">Docs Setup</a>
              <button onClick={() => setShowDocs(true)} className="landing-nav-link-btn">
                Documentation
              </button>
            </div>
            <div className="flex items-center gap-4">
              <button onClick={() => setView('chat')} className="landing-nav-cta">
                Launch Mentor
              </button>
              <button 
                onClick={() => setView('profile')} 
                className="w-8 h-8 rounded border border-orange-500/30 bg-[#181C26] flex items-center justify-center hover:border-orange-500 transition-all cursor-pointer"
                title="View Profile Stats"
              >
                {user?.avatar_url ? (
                  <img src={user.avatar_url} alt={user.display_name} className="w-full h-full rounded object-cover" />
                ) : (
                  <span className="text-xs font-bold text-orange-500">
                    {user?.display_name ? user.display_name[0].toUpperCase() : 'U'}
                  </span>
                )}
              </button>
            </div>
          </nav>

          {/* Hero Section */}
          <header className="hero-section">
            <h1 className="hero-title" style={{ marginTop: '30px' }}>
              Your Personal <span>AI Mentor</span> for All Fields of Engineering
            </h1>
            <p className="hero-subtitle">
              Say goodbye to generalized AI chat. EduMentor is a specialized, voice-driven platform
              designed to help you understand complex calculations, analyze structures, write clean algorithms,
              and conceptualize physical systems step-by-step.
            </p>
            <div className="hero-ctas">
              <button onClick={() => setView('chat')} className="cta-primary">
                Start Talking Now
              </button>
              <a href="#features" className="cta-secondary" style={{ textDecoration: 'none', display: 'inline-block' }}>
                Explore Disciplines
              </a>
            </div>
          </header>

          {/* Features / Disciplines Grid Section */}
          <section id="features" className="features-section">
            <div className="section-header">
              <h2 className="section-title">Support Across Every Major Discipline</h2>
              <p className="section-subtitle">A foundational guide across essential engineering disciplines.</p>
            </div>
            <div className="cards-grid">
              {disciplines.map((d, idx) => (
                <div key={idx} className="feature-card">
                  <div className="feature-card-icon-wrap" style={{ background: d.color }}>
                    {d.icon}
                  </div>
                  <h3 className="feature-card-title">{d.title}</h3>
                  <p className="feature-card-desc">{d.desc}</p>
                </div>
              ))}
            </div>
          </section>          {/* Developer SDK Integration Section */}
          <section id="sdk" className="docs-section" style={{ borderTop: '1px solid var(--border-default)', paddingTop: '60px', paddingBottom: '20px' }}>
            <div className="section-header">
              <h2 className="section-title">Developer Client SDK</h2>
              <p className="section-subtitle">Integrate EduMentor's real-time voice & engineering tutor pipeline into your own apps.</p>
            </div>
            <div className="docs-grid-layout" style={{ alignItems: 'stretch' }}>
              <div className="docs-card-highlight" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className="docs-card-icon-title">
                    <Terminal className="text-indigo-600" size={24} />
                    <h3>EduMentor Voice SDK</h3>
                  </div>
                  <p style={{ margin: 0 }}>
                    A lightweight, framework-agnostic client library that wraps Web Audio contexts, microphone capture (via high-performance AudioWorklet threads), and WebSocket handlers. Automatically handles gapless queue playback, voice personas, and client-side barge-in/interruptions.
                  </p>
                </div>
                <div className="docs-action-buttons" style={{ marginTop: '20px' }}>
                  <a href="/edumentor-sdk.js" download className="docs-btn-primary" style={{ textDecoration: 'none' }}>
                    <Download size={16} /> Download JS SDK File
                  </a>
                  <a href="/audio-processor.js" download className="docs-btn-secondary" style={{ textDecoration: 'none' }}>
                    Download Audio Worklet <ExternalLink size={14} />
                  </a>
                </div>
              </div>
              
              <div style={{
                background: '#0B0F19',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: 'var(--radius-xl)',
                padding: '24px',
                fontFamily: 'monospace',
                fontSize: '11px',
                lineHeight: '1.6',
                color: '#A5B4FC',
                overflowX: 'auto',
                boxShadow: 'var(--shadow-md)',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                boxSizing: 'border-box'
              }}>
                <div style={{ color: '#6366F1', fontWeight: 'bold', marginBottom: '8px' }}>// Initialize the Voice SDK</div>
                <div><span style={{ color: '#F472B6' }}>import</span> &#123; EduMentorVoiceSDK &#125; <span style={{ color: '#F472B6' }}>from</span> <span style={{ color: '#34D399' }}>'./edumentor-sdk.js'</span>;</div>
                <br />
                <div><span style={{ color: '#F472B6' }}>const</span> sdk = <span style={{ color: '#F472B6' }}>new</span> <span style={{ color: '#60A5FA' }}>EduMentorVoiceSDK</span>(&#123;</div>
                <div>&nbsp;&nbsp;wsUrl: <span style={{ color: '#34D399' }}>'ws://localhost:8000/ws/voice'</span>,</div>
                <div>&nbsp;&nbsp;token: <span style={{ color: '#34D399' }}>'YOUR_JWT_ACCESS_TOKEN'</span>,</div>
                <div>&nbsp;&nbsp;accent: <span style={{ color: '#34D399' }}>'af_bella'</span>, <span style={{ color: '#6B7280' }}>// Voice style code</span></div>
                <div>&nbsp;&nbsp;onTranscript: (msg) =&gt; console.log(<span style={{ color: '#34D399' }}>"User said:"</span>, msg.text),</div>
                <div>&nbsp;&nbsp;onTextUpdate: (msg) =&gt; console.log(<span style={{ color: '#34D399' }}>"AI token:"</span>, msg.text),</div>
                <div>&nbsp;&nbsp;onInterrupt: () =&gt; console.log(<span style={{ color: '#34D399' }}>"AI Interrupted!"</span>)</div>
                <div>&#125;);</div>
                <br />
                <div><span style={{ color: '#6B7280' }}>// Establish session and start microphone</span></div>
                <div><span style={{ color: '#F472B6' }}>await</span> sdk.connect();</div>
                <div><span style={{ color: '#F472B6' }}>await</span> sdk.startRecording();</div>
              </div>
            </div>
          </section>
          {/* Documentation Section */}
          <section id="docs" className="docs-section">
            <div className="section-header">
              <h2 className="section-title">Getting Started & Documentation</h2>
              <p className="section-subtitle">Learn how to set up the EduMentor workspace locally on your system.</p>
            </div>
            <div className="docs-grid-layout">
              <div className="docs-card-highlight">
                <div className="docs-card-icon-title">
                  <FileText className="text-indigo-600" size={24} />
                  <h3>Local Repository Documentation</h3>
                </div>
                <p>
                  Read the complete setup guide, architectural specifications, performance tuning tips, and troubleshooting options directly from the project repository's README.
                </p>
                <div className="docs-action-buttons">
                  <button onClick={() => setShowDocs(true)} className="docs-btn-primary">
                    <BookOpen size={16} /> Read Full Docs (README)
                  </button>
                  <a href="/README.md" target="_blank" rel="noreferrer" className="docs-btn-secondary">
                    View Raw File <ExternalLink size={14} />
                  </a>
                </div>
              </div>
              <div className="docs-features-list">
                <div className="docs-feature-item">
                  <div className="docs-feat-dot" />
                  <div>
                    <h4>Real-time Voice Pipeline</h4>
                    <p>Uses high-performance AudioWorklet streams with Whisper STT and Kokoro TTS to achieve 2-4 seconds target latency.</p>
                  </div>
                </div>
                <div className="docs-feature-item">
                  <div className="docs-feat-dot" />
                  <div>
                    <h4>100% Private & Local</h4>
                    <p>No external APIs or data leaks. Your chats, documents, and voice responses stay entirely on your physical machine.</p>
                  </div>
                </div>
                <div className="docs-feature-item">
                  <div className="docs-feat-dot" />
                  <div>
                    <h4>Broad Engineering Syllabus</h4>
                    <p>Optimized prompts allow the mentor to guide you in solving complex calculations and systems engineering questions.</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Floating Chatbot Launcher widget */}
          <div className="floating-launcher-wrap">
            <div className="launcher-popover" onClick={() => setView('chat')} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '180px' }}>
              <motion.span
                key={activeMessageIdx}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={{ duration: 0.3 }}
                style={{ display: 'inline-block' }}
              >
                {launcherMessages[activeMessageIdx]}
              </motion.span>
            </div>
            <button className="floating-launcher-btn" onClick={() => setView('chat')} aria-label="Talk to AI Mentor">
              <img src="/mascot.png" alt="EduMentor Logo" />
            </button>
          </div>
        </div>
      ) : (
        <motion.div
          className="app-shell"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
        >
          <ErrorBoundary onReset={() => window.location.reload()}>
            <Sidebar
              grouped={grouped}
              activeId={activeId}
              onSelect={selectConversation}
              onDelete={deleteConversation}
              onNewChat={createConversation}
              isOpen={sidebarOpen}
              onClose={() => setSidebarOpen(false)}
            />
          </ErrorBoundary>

          <div className="workspace">
            {/* Header */}
            <header className="workspace-header">
              <div className="header-left">
                <button
                  className="home-btn mr-2"
                  onClick={() => setView('landing')}
                  aria-label="Back to home"
                >
                  <Home size={18} />
                </button>
                <button
                  className="hamburger-btn"
                  onClick={() => setSidebarOpen(true)}
                  aria-label="Open sidebar"
                >
                  <PanelLeft size={18} />
                </button>
                <div className="header-logo">
                  <div className="header-logo-icon" style={{ background: 'transparent', boxShadow: 'none', padding: 0 }}>
                    <img src="/mascot.png" alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain', mixBlendMode: 'multiply' }} />
                  </div>
                  <div>
                    <div className="header-title">EduMentor</div>
                    <div className="header-subtitle">
                      {activeConversation?.title === 'New Conversation' ? 'AI Voice Tutor' : activeConversation?.title ?? 'AI Voice Tutor'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {/* Keyboard Shortcuts Toggle Button */}
                <button
                  onClick={() => setShortcutsEnabled(!shortcutsEnabled)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    shortcutsEnabled
                      ? 'bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/30 dark:border-indigo-900/50 dark:text-indigo-300'
                      : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100 dark:bg-slate-800/30 dark:border-slate-700/50 dark:text-slate-400'
                  }`}
                  title={shortcutsEnabled ? "Disable Spacebar shortcut" : "Enable Spacebar shortcut"}
                >
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: shortcutsEnabled ? 'var(--accent-indigo)' : 'var(--text-tertiary)' }} />
                  <span>Spacebar {shortcutsEnabled ? 'Active' : 'Disabled'}</span>
                </button>

                {/* Connection Status */}
                <StatusBar
                  connectionState={connectionState}
                  status={status}
                  isRecording={isRecording}
                  isProcessing={isProcessing}
                  isPlaying={isPlaying}
                  conversationState={conversationState}
                  manualReconnect={manualReconnect}
                  reconnectAttempt={
                    // Parse attempt number from status string "reconnecting:N"
                    status?.startsWith('reconnecting:')
                      ? status.split(':')[1]
                      : undefined
                  }
                />

                {/* User Dropdown Profile/Logout Menu (Part 2) */}
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setAvatarDropdownOpen(!avatarDropdownOpen)}
                    className="flex items-center gap-2 border border-[var(--border-default)] bg-[var(--bg-primary)] hover:border-[var(--accent-indigo)] p-1.5 rounded-none cursor-pointer transition-all shadow-sm"
                    title="User Account"
                  >
                    {user?.avatar_url ? (
                      <img src={user.avatar_url} alt={user.display_name} className="w-6 h-6 rounded-none object-cover" />
                    ) : (
                      <div className="w-6 h-6 rounded-none bg-indigo-950/20 border border-indigo-500/30 flex items-center justify-center text-[10px] font-bold text-indigo-400">
                        {user?.display_name ? user.display_name[0].toUpperCase() : 'U'}
                      </div>
                    )}
                  </button>
                  
                  {avatarDropdownOpen && (
                    <>
                      {/* Dropdown Menu */}
                      <div className="absolute right-0 mt-2 w-48 border border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg rounded-none py-1 z-50 font-sans text-xs select-none text-[var(--text-secondary)]">
                        <div className="px-3 py-2 border-b border-[var(--border-default)]">
                          <div className="font-extrabold text-[var(--text-primary)] truncate">{user?.display_name}</div>
                          <div className="text-[9.5px] text-[var(--text-muted)] truncate mt-0.5">{user?.email}</div>
                        </div>
                        
                        <button
                          onClick={() => {
                            setView('profile');
                            setAvatarDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-2.5 cursor-pointer font-semibold"
                        >
                          <UserIcon size={13} className="text-[var(--text-muted)]" /> Profile Stats
                        </button>
                        
                        <button
                          onClick={() => {
                            setView('dashboard');
                            setAvatarDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-2.5 cursor-pointer font-semibold"
                        >
                          <LayoutDashboard size={13} className="text-[var(--text-muted)]" /> Insights Dashboard
                        </button>
                        
                        <button
                          onClick={() => {
                            setView('settings');
                            setAvatarDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-2.5 cursor-pointer font-semibold"
                        >
                          <Settings size={13} className="text-[var(--text-muted)]" /> Settings View
                        </button>
                        
                        <div className="border-t border-[var(--border-default)] my-1" />
                        
                        <button
                          onClick={() => {
                            logout();
                            setAvatarDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 text-rose-500 hover:bg-rose-950/20 transition-colors flex items-center gap-2.5 cursor-pointer font-semibold"
                        >
                          <LogOut size={13} /> Sign Out
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </header>

            {/* MAIN WORKSPACE CONTENT */}
            {view === 'profile' ? (
              <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 relative z-10 select-none bg-[var(--bg-secondary)]">
                <Profile onBack={() => setView('chat')} setView={setView} />
              </div>
            ) : view === 'dashboard' ? (
              <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 relative z-10 select-none bg-[var(--bg-secondary)]">
                <AnalyticsOverview onBack={() => setView('chat')} />
              </div>
            ) : view === 'settings' ? (
              <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 relative z-10 select-none bg-[var(--bg-secondary)]">
                <SettingsView onBack={() => setView('chat')} />
              </div>
            ) : (
              <div className="flex-1 overflow-hidden flex flex-col relative z-10 pt-4">
                <div className="flex-1 overflow-hidden flex flex-col relative">
                  {messages.length === 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.2 }}
                      className="flex-1 flex flex-col items-center justify-center p-8 text-center"
                      style={{ gap: '0px' }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {/* FIX 1 — Isolate MentorCharacter: Three.js / WebGL failures are common.
                            A crashed avatar must NOT take down the whole chat area. */}
                        <ErrorBoundary onReset={() => window.location.reload()}>
                          <motion.div
                            layoutId="mentor-canvas"
                            className="mentor-canvas-wrapper idle-mode"
                          >
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
                          </motion.div>
                        </ErrorBoundary>
                      </div>
                      <div style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: '4px',
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
                          fontSize: '14px',
                          fontWeight: '550',
                          color: 'var(--text-secondary)',
                          margin: 0,
                        }}>
                          Your Engineering Mentor
                        </p>
                        <p style={{
                          fontSize: '13px',
                          color: 'var(--text-muted)',
                          margin: 0,
                          lineHeight: '1.4',
                          maxWidth: '280px',
                        }}>
                          Press the mic below to start our session.
                        </p>
                      </div>
                    </motion.div>
                  )}

                  {/* FIX 1 — Isolate MessageList: if ONE message bubble throws (e.g.
                      malformed markdown from a streamed response), only the message
                      list resets — the voice pipeline keeps running.
                      Only render when there are messages — the welcome screen above
                      already handles the empty state so we don't double-render. */}
                  {messages.length > 0 && (
                  <ErrorBoundary onReset={resetMessageList}>
                    <MessageList
                      messages={messages}
                      conversationId={activeId}
                      currentSpokenWordIndex={currentSpokenWordIndex}
                      isSpeakingTextSync={isSpeakingTextSync}
                      analyserNode={analyserNode}
                      conversationState={conversationState}
                      defaultAvatarUrl={defaultAvatarUrl}
                      onSnapshot={saveMessageSnapshot}
                    />
                  </ErrorBoundary>
                  )}
                </div>

                {/* Fixed bottom controls */}
                <footer className="voice-zone shrink-0">
                  <div className="w-full max-w-2xl mx-auto flex flex-col gap-3">
                    <div className="flex justify-center pb-1">
                      <VoiceOrb
                        isRecording={isRecording}
                        isProcessing={isProcessing}
                        isPlaying={isPlaying}
                        conversationState={conversationState}
                        onClick={toggleRecording}
                        shortcutsEnabled={shortcutsEnabled}
                      />
                    </div>
                  </div>
                 </footer>
              </div>
            )}

            {/* FIX 4 — Duplicate tab banner */}
            {isDuplicateTab && (
              <div
                role="alert"
                style={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: 0,
                  zIndex: 9999,
                  background: '#FEF3C7',
                  borderBottom: '1px solid #F59E0B',
                  color: '#92400E',
                  fontSize: '13px',
                  fontWeight: '500',
                  padding: '8px 16px',
                  textAlign: 'center',
                }}
              >
                This conversation is open in another tab. Voice input is disabled here to prevent conflicts.
              </div>
            )}

            {/* Soft radial glow behind the 3D character */}
            <div
              className={`mentor-glow ${messages.length > 0 ? 'chat-mode' : 'idle-mode'}`}
              style={{ backgroundColor: glowColor }}
            />
          </div>
        </motion.div>
      )}

      {showDocs && (
        <div className="docs-modal-overlay" onClick={() => setShowDocs(false)}>
          <div className="docs-modal" onClick={(e) => e.stopPropagation()}>
            <header className="docs-modal-header">
              <h3 className="docs-modal-title">Repository Documentation</h3>
              <button className="docs-modal-close" onClick={() => setShowDocs(false)} aria-label="Close documentation">
                <X size={18} />
              </button>
            </header>
            <div className="docs-modal-content">
              {isLoadingReadme ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '12px' }}>
                  <div className="voice-orb-spinner" style={{ position: 'relative', width: '32px', height: '32px', borderTopColor: 'var(--accent-indigo)' }} />
                  <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>Loading README.md...</p>
                </div>
              ) : (
                <MarkdownViewer text={readmeContent} />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
