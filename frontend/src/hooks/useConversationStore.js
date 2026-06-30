import { useMemo } from 'react';
import { chatStore } from '../stores/chatStore';

function groupByDate(conversations) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yest = new Date(today);
  yest.setDate(yest.getDate() - 1);

  const groups = { today: [], yesterday: [], previous: [] };

  for (const conv of conversations) {
    const d = new Date(conv.createdAt);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (day >= today) {
      groups.today.push(conv);
    } else if (day >= yest) {
      groups.yesterday.push(conv);
    } else {
      groups.previous.push(conv);
    }
  }
  return groups;
}

export function useConversationStore() {
  const conversations = chatStore.useStore((s) => s.conversations);
  const activeId = chatStore.useStore((s) => s.activeId);

  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeId) || null,
    [conversations, activeId]
  );

  const grouped = useMemo(() => groupByDate(conversations), [conversations]);

  return {
    conversations,
    activeId,
    activeConversation,
    grouped,
    createConversation: chatStore.getState().createConversation,
    selectConversation: chatStore.getState().selectConversation,
    deleteConversation: chatStore.getState().deleteConversation,
    addMessage: chatStore.getState().addMessage,
    updateStreamingMessage: chatStore.getState().updateStreamingMessage,
    setStreamingMessageText: chatStore.getState().setStreamingMessageText,
    finishStreamingMessage: chatStore.getState().finishStreamingMessage,
    saveMessageSnapshot: chatStore.getState().saveMessageSnapshot,
  };
}
