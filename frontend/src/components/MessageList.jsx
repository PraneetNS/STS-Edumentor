/**
 * MessageList — Renders the conversation history with premium Neo-Brutalist cards.
 */
import React, { useEffect, useRef, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User, AlertTriangle } from 'lucide-react';
import { MascotOwl } from './MascotOwl';
import { MarkdownViewer } from './MarkdownViewer';
import { UserMessageText } from './UserMessageText';
import { extractVisualBlocks } from '../utils/visualBlockExtractor';
import CodeStrategy from '../features/chat/components/DisplayPanel/CodeStrategy';
import MermaidStrategy from '../features/chat/components/DisplayPanel/MermaidStrategy';
import RoadmapStrategy from '../features/chat/components/DisplayPanel/RoadmapStrategy';
import ComparisonTableStrategy from '../features/chat/components/DisplayPanel/ComparisonTableStrategy';
import ChecklistStrategy from '../features/chat/components/DisplayPanel/ChecklistStrategy';

const strategyMap = {
  code: CodeStrategy,
  mermaid: MermaidStrategy,
  roadmap: RoadmapStrategy,
  workflow: RoadmapStrategy,
  table: ComparisonTableStrategy,
  checklist: ChecklistStrategy,
};

const Message = memo(function Message({
  msg, 
  currentSpokenWordIndex, 
  isSpeakingTextSync,
  analyserNode,
  conversationState,
  isActiveMessage,
  onSnapshot,
  onSendFollowup
}) {
  const isUser = msg.role === 'user';
  const isStreaming = msg.isStreaming;
  const blocks = !isUser ? extractVisualBlocks(msg.text) : [];
  const labelText = isUser ? 'You' : 'EDI';

  return (
    <motion.div
      className={`message-wrapper message flex items-start gap-4 mb-6 ${isUser ? 'user flex-row-reverse justify-start' : 'assistant justify-start'}`}
      initial={{ opacity: 0, y: 15, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25 }}
      layout
    >
      {/* Avatar Container */}
      <div className={`avatar-wrapper shrink-0 w-9 h-9 rounded-full flex items-center justify-center ${isUser ? 'bg-blue-500 text-white' : 'bg-white border border-neutral-200 p-0.5 shadow-sm'}`}>
        {isUser ? (
          <User size={16} strokeWidth={2.5} />
        ) : (
          <MascotOwl 
            state={isActiveMessage ? conversationState.toLowerCase() : 'idle'} 
            size="100%" 
          />
        )}
      </div>

      {/* Message Balloon */}
      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Label */}
        <span className="font-sans font-semibold text-[10px] text-neutral-500 tracking-wider px-1">
          {labelText}
        </span>

        <div className={`msg-bubble ${isUser ? 'user' : 'assistant'}`}>
          {isStreaming ? (
            <MarkdownViewer text={msg.text || ''} isStreaming={true} />
          ) : (
            isUser ? <UserMessageText text={msg.text} /> : <MarkdownViewer text={msg.text} />
          )}

          {/* Visual Strategies (Graphs, code blocks, checklists) */}
          {blocks.length > 0 && (
            <div className="mt-4 flex flex-col gap-4 select-text">
              {blocks.map((block) => {
                const StrategyComponent = strategyMap[block.type] || CodeStrategy;
                return (
                  <div 
                    key={block.id} 
                    className="w-full max-w-full overflow-hidden border border-neutral-800 rounded-xl shadow-sm bg-[#0f172a]"
                  >
                    <StrategyComponent block={block} />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Followup suggestions */}
        {!isUser && msg.followup && (
          <div className="mt-2.5 flex flex-col items-start gap-1 select-none">
            <span className="font-sans font-semibold text-[9px] text-neutral-400 pl-0.5">
              Suggested Followup
            </span>
            <button
              onClick={() => onSendFollowup?.(msg.followup)}
              className="flex items-center gap-1.5 font-sans font-semibold text-[11px] text-blue-700 bg-blue-50 border border-blue-100 hover:bg-blue-100 hover:border-blue-200 px-3.5 py-1.5 rounded-full shadow-sm transition-all cursor-pointer text-left"
            >
              <span>💡</span>
              <span>{msg.followup}</span>
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
});

function MessageListSkeleton() {
  return (
    <div className="message-area flex flex-col gap-4 p-6" role="status" aria-label="Loading conversation">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="border border-neutral-200 bg-white p-4 rounded-xl shadow-sm animate-pulse max-w-md"
          style={{ height: '70px', opacity: 0.5 }}
        >
          <div className="h-3.5 bg-gray-300 w-1/3 mb-2 rounded" />
          <div className="h-3 bg-gray-200 w-full rounded" />
        </div>
      ))}
    </div>
  );
}

function MessageListEmpty() {
  return (
    <div
      className="message-area flex flex-col items-center justify-center text-center p-12 min-h-[50vh]"
      aria-label="No messages yet"
    >
      <div className="w-32 h-32 mb-6">
        <MascotOwl state="listening" size="100%" />
      </div>
      <div className="bg-white border border-neutral-200 p-6 rounded-2xl max-w-sm shadow-sm">
        <h3 className="font-sans font-bold text-sm text-neutral-850 mb-1">EDI is ready to talk!</h3>
        <p className="font-sans text-xs text-neutral-500 leading-relaxed">
          Ask me anything about engineering concepts, coding architectures, structural mechanics, or roadmap sequences.
        </p>
      </div>
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
  onSnapshot,
  onSendFollowup
}) {
  const bottomRef = useRef(null);

  if (messages == null) return <MessageListSkeleton />;

  // Auto-scroll when new items arrive
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    const el = bottomRef.current;
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, messages[messages.length - 1]?.text]);

  if (messages.length === 0) return <MessageListEmpty />;

  const lastAssistantMsgIndex = [...messages].reverse().findIndex(m => m.role === 'assistant');
  const activeMessageId = lastAssistantMsgIndex !== -1
    ? messages[messages.length - 1 - lastAssistantMsgIndex].id
    : null;

  return (
    <div className="message-area p-6 overflow-y-auto flex-1 select-none" role="log" aria-live="polite">
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
            onSendFollowup={onSendFollowup}
          />
        ))}
      </AnimatePresence>

      <div ref={bottomRef} className="h-4" />
    </div>
  );
});
