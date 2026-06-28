/**
 * MessageList — Renders the conversation history with premium glass animations.
 * Now embeds the expressive 3D Mentor Character for EDI's messages.
 */
import React, { useEffect, useRef, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User } from 'lucide-react';
import { MentorCharacter } from './MentorCharacter';
import { MarkdownViewer } from './MarkdownViewer';
import { UserMessageText } from './UserMessageText';

const Message = memo(function Message({
  msg, 
  currentSpokenWordIndex, 
  isSpeakingTextSync,
  analyserNode,
  conversationState,
  isActiveMessage,
  defaultAvatarUrl,
  onSnapshot
}) {
  const isUser = msg.role === 'user';
  const isStreaming = msg.isStreaming;

  const labelText = isUser ? 'You' : 'EDI';

  const avatarUrl = msg.avatarSnapshot || defaultAvatarUrl;

  return (
    <motion.div
      className={`message ${isUser ? 'user' : 'assistant'}`}
      initial={{ opacity: 0, y: 15, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, type: "spring", bounce: 0.2 }}
      layout
    >
      {/* Mini Avatar / Face */}
      <div className={`msg-avatar ${isUser ? 'user-avatar' : 'ai-avatar'}`}>
        {isUser ? (
          <User size={14} />
        ) : avatarUrl && !isActiveMessage ? (
          <img src={avatarUrl} className="mentor-snapshot-img" alt="EDI" />
        ) : (
          <div className="compact-mentor-wrap">
            <MentorCharacter
              state={isActiveMessage ? conversationState.toLowerCase() : 'idle'}
              analyserNode={isActiveMessage ? analyserNode : undefined}
              onSnapshot={isActiveMessage ? (dataUrl) => onSnapshot && onSnapshot(msg.id, dataUrl) : undefined}
            />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="message-content flex flex-col gap-1">
        <div className={`msg-label ${isUser ? 'text-right' : ''}`}>
          {labelText}
        </div>
        <div className={`msg-bubble glass${isStreaming && !msg.text?.trim() ? ' msg-bubble--thinking' : ''}${isStreaming && msg.text?.trim() ? ' streaming-text' : ''}`}>
          {isStreaming ? (
            <MarkdownViewer text={msg.text || ''} isStreaming={true} />
          ) : (
            isUser ? <UserMessageText text={msg.text} /> : <MarkdownViewer text={msg.text} />
          )}
        </div>
      </div>
    </motion.div>
  );
});

// FIX 6 — Loading skeleton shown while messages array is null/undefined
function MessageListSkeleton() {
  return (
    <div className="message-area" role="status" aria-label="Loading conversation">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            height: '48px',
            borderRadius: '12px',
            background: 'rgba(0,0,0,0.06)',
            margin: '8px 16px',
            animation: 'pulse 1.5s ease-in-out infinite',
            opacity: 0.5,
          }}
        />
      ))}
    </div>
  );
}

// FIX 6 — Empty state shown when messages array is present but empty
function MessageListEmpty() {
  return (
    <div
      className="message-area"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-muted)',
        fontSize: '14px',
        padding: '2rem',
        textAlign: 'center',
      }}
      aria-label="No messages yet"
    >
      Ask me anything about your engineering studies
    </div>
  );
}

export const MessageList = memo(function MessageList({
  messages,
  currentSpokenWordIndex,
  isSpeakingTextSync,
  analyserNode,
  conversationState,
  defaultAvatarUrl,
  onSnapshot
}) {
  const bottomRef = useRef(null);

  // FIX 6 — Guard: null/undefined during initial load → loading skeleton
  if (messages == null) return <MessageListSkeleton />;

  // Auto-scroll to the bottom of the timeline whenever a new message is added
  // or when an existing streaming assistant message receives new token updates.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    const el = bottomRef.current;
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, messages[messages.length - 1]?.text]);

  // FIX 6 — Guard: empty array → friendly empty state
  if (messages.length === 0) return <MessageListEmpty />;

  // The last assistant message is the "active" one for animation purposes
  const lastAssistantMsgIndex = [...messages].reverse().findIndex(m => m.role === 'assistant');
  const activeMessageId = lastAssistantMsgIndex !== -1
    ? messages[messages.length - 1 - lastAssistantMsgIndex].id
    : null;

  return (
    <div className="message-area" role="log" aria-live="polite">
      <AnimatePresence initial={false}>
        {messages.map(msg => (
          <Message
            key={msg.id}
            msg={msg}
            currentSpokenWordIndex={currentSpokenWordIndex}
            isSpeakingTextSync={isSpeakingTextSync}
            analyserNode={analyserNode}
            conversationState={conversationState}
            isActiveMessage={msg.id === activeMessageId}
            defaultAvatarUrl={defaultAvatarUrl}
            onSnapshot={onSnapshot}
          />
        ))}
      </AnimatePresence>

      <div ref={bottomRef} className="h-4" />
    </div>
  );
});
