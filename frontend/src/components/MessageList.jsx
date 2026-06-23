/**
 * MessageList — Renders the conversation history with premium glass animations.
 * Now embeds the expressive 3D Mentor Character for EDI's messages.
 */
import React, { useEffect, useRef, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User } from 'lucide-react';
import { SpeakingText } from './SpeakingText';
import { MentorCharacter } from './MentorCharacter';
import { MarkdownViewer } from './MarkdownViewer';

/**
 * StreamingContent — Smart renderer for in-progress assistant messages.
 *
 * Splits text on markdown "show block" boundaries (lines starting with ###, ```, 
 * or numbered lists after a blank line) so that the spoken portion gets 
 * word-by-word SpeakingText highlighting while roadmaps/code render via 
 * MarkdownViewer instead of showing raw markdown syntax.
 */
const SHOW_BLOCK_SPLIT = /(\n\n(?:#{1,3} |```|\d+\. |\- ))/;

function StreamingContent({ text, currentWordIndex, isSpeakingTextSync }) {
  if (!text) return null;

  // Split on double-newline followed by a markdown block marker
  const parts = text.split(SHOW_BLOCK_SPLIT);

  // Recombine: every odd index is the separator that got captured; 
  // join it back with the following segment.
  const segments = [];
  let i = 0;
  while (i < parts.length) {
    if (i + 1 < parts.length && SHOW_BLOCK_SPLIT.test(parts[i + 1])) {
      // The next part is a separator — merge it with the part after
      segments.push({ type: 'text', content: parts[i] });
      segments.push({ type: 'markdown', content: parts[i + 1] + (parts[i + 2] || '') });
      i += 3;
    } else {
      segments.push({ type: 'text', content: parts[i] });
      i += 1;
    }
  }

  // Count words in all plain-text segments before each, to maintain word index offsets
  let wordsBefore = 0;
  return (
    <span className="speaking-active" style={{ display: 'block' }}>
      {segments.map((seg, idx) => {
        if (seg.type === 'markdown') {
          return (
            <div key={idx} className="mt-2">
              <MarkdownViewer text={seg.content} />
            </div>
          );
        }
        // Plain-text spoken segment
        const segWords = seg.content ? seg.content.split(' ').length : 0;
        const offsetIndex = wordsBefore;
        wordsBefore += segWords;
        return (
          <SpeakingText
            key={idx}
            text={seg.content}
            currentWordIndex={currentWordIndex - offsetIndex}
            isSpeakingTextSync={isSpeakingTextSync}
            isStreaming={true}
          />
        );
      })}
    </span>
  );
}

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
              <StreamingContent
                text={msg.text}
                currentWordIndex={currentSpokenWordIndex}
                isSpeakingTextSync={isSpeakingTextSync}
              />
            ) : (
              // Thinking dots
              <div className="flex items-center gap-1.5 h-5 my-0.5" style={{ display: 'flex' }}>
                {[0,1,2].map(i => (
                  <motion.span
                    key={i}
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: 'var(--accent-indigo)', display: 'inline-block' }}
                    animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
                    transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            )
          ) : (
            isUser ? msg.text : <MarkdownViewer text={msg.text} />
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
