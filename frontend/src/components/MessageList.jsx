/**
 * MessageList — Renders the conversation history with premium glass animations.
 * Now embeds the expressive 3D Mentor Character for EDI's messages.
 */
import React, { useEffect, useRef, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User } from 'lucide-react';
import { SpeakingText } from './SpeakingText';
import { MentorCharacter } from './MentorCharacter';

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
      <div className="flex flex-col gap-1" style={{ maxWidth: 'calc(100% - 50px)' }}>
        <div className={`msg-label ${isUser ? 'text-right' : ''}`}>
          {labelText}
        </div>
        <div className="msg-bubble glass">
          {isStreaming ? (
            msg.text ? (
              <span className="speaking-active">
                <SpeakingText
                  text={msg.text}
                  currentWordIndex={currentSpokenWordIndex}
                  isSpeakingTextSync={isSpeakingTextSync}
                />
              </span>
            ) : (
              // Thinking dots
              <span className="inline-flex items-center gap-1.5 h-6">
                {[0,1,2].map(i => (
                  <motion.span
                    key={i}
                    className="inline-block w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--accent-indigo)' }}
                    animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
                    transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </span>
            )
          ) : (
            msg.text
          )}
        </div>
      </div>
    </motion.div>
  );
});

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

  useEffect(() => {
    const el = bottomRef.current;
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, messages[messages.length - 1]?.text]);

  const hasContent = messages.length > 0;
  
  // The last assistant message is the "active" one for animation purposes
  const lastAssistantMsgIndex = [...messages].reverse().findIndex(m => m.role === 'assistant');
  const activeMessageId = lastAssistantMsgIndex !== -1 
    ? messages[messages.length - 1 - lastAssistantMsgIndex].id 
    : null;

  return (
    <div className="message-area" role="log" aria-live="polite">
      {hasContent && (
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
      )}

      <div ref={bottomRef} className="h-4" />
    </div>
  );
});
