/**
 * useConversationStore
 * 
 * Manages conversation history with localStorage persistence.
 * Groups conversations by Today / Yesterday / Previous.
 */
import { useState, useCallback, useMemo } from 'react';

const STORAGE_KEY = 'edumentor_v2_conversations';

function generateId() {
  return 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) {
    console.warn('[Store] Failed to load conversations:', e);
  }
  return null;
}

function saveToStorage(convs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs));
  } catch (e) {
    console.warn('[Store] Failed to save conversations:', e);
  }
}

function createNewConversation() {
  return {
    id:        generateId(),
    title:     'New Conversation',
    createdAt: new Date().toISOString(),
    messages:  [],
  };
}

function getInitialState() {
  const saved = loadFromStorage();
  if (saved) {
    return { conversations: saved, activeId: saved[0].id };
  }
  const initial = createNewConversation();
  return { conversations: [initial], activeId: initial.id };
}

function groupByDate(conversations) {
  const now   = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yest  = new Date(today); yest.setDate(yest.getDate() - 1);

  const groups = { today: [], yesterday: [], previous: [] };

  for (const conv of conversations) {
    const d = new Date(conv.createdAt);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (day >= today)               groups.today.push(conv);
    else if (day >= yest)           groups.yesterday.push(conv);
    else                            groups.previous.push(conv);
  }
  return groups;
}

export function useConversationStore() {
  const initial = useMemo(() => getInitialState(), []);
  const [conversations, setConversations] = useState(initial.conversations);
  const [activeId, setActiveId]           = useState(initial.activeId);

  const activeConversation = useMemo(
    () => conversations.find(c => c.id === activeId) || null,
    [conversations, activeId]
  );

  const grouped = useMemo(() => groupByDate(conversations), [conversations]);

  // ── Mutators ──────────────────────────────────────────────────────────────

  const createConversation = useCallback(() => {
    const conv = createNewConversation();
    setConversations(prev => {
      const updated = [conv, ...prev];
      saveToStorage(updated);
      return updated;
    });
    setActiveId(conv.id);
    return conv.id;
  }, []);

  const selectConversation = useCallback((id) => {
    setActiveId(id);
  }, []);

  const deleteConversation = useCallback((id, e) => {
    e?.stopPropagation();
    setConversations(prev => {
      const updated = prev.filter(c => c.id !== id);
      saveToStorage(updated);

      // If we deleted the active one, switch to the next available
      setActiveId(current => {
        if (current !== id) return current;
        if (updated.length > 0) return updated[0].id;
        // No conversations left — create a fresh one
        const fresh = createNewConversation();
        const withFresh = [fresh];
        saveToStorage(withFresh);
        setConversations(withFresh);
        return fresh.id;
      });

      return updated;
    });
  }, []);

  const addMessage = useCallback((role, text, extra = {}) => {
    const msgId = extra.id || (role === 'user' ? 'u-' : 'a-') + Date.now();
    setConversations(prev => {
      const updated = prev.map(conv => {
        if (conv.id !== activeId) return conv;
        const msgs = [...conv.messages];
        msgs.push({
          id: msgId,
          role,
          text,
          timestamp: new Date().toISOString(),
          ...extra
        });

        // Auto-generate title from first user message
        let title = conv.title;
        if (title === 'New Conversation' && role === 'user' && text) {
          title = text.length > 36 ? text.slice(0, 36) + '…' : text;
        }

        return { ...conv, title, messages: msgs };
      });
      saveToStorage(updated);
      return updated;
    });
    return msgId;
  }, [activeId]);

  const updateStreamingMessage = useCallback((msgId, textDelta) => {
    setConversations(prev => {
      const updated = prev.map(conv => {
        if (conv.id !== activeId) return conv;
        const msgs = conv.messages.map(m => {
          if (m.id === msgId) {
            return { ...m, text: m.text + textDelta };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return updated;
    });
  }, [activeId]);

  const setStreamingMessageText = useCallback((msgId, fullText) => {
    setConversations(prev => {
      const updated = prev.map(conv => {
        if (conv.id !== activeId) return conv;
        const msgs = conv.messages.map(m => {
          if (m.id === msgId) {
            return { ...m, text: fullText };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return updated;
    });
  }, [activeId]);

  const finishStreamingMessage = useCallback((msgId) => {
    setConversations(prev => {
      const updated = prev.map(conv => {
        if (conv.id !== activeId) return conv;
        const msgs = conv.messages.map(m => {
          if (m.id === msgId) {
            const { isStreaming, ...rest } = m;
            return rest;
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return updated;
    });
  }, [activeId]);

  return {
    conversations,
    activeId,
    activeConversation,
    grouped,
    createConversation,
    selectConversation,
    deleteConversation,
    addMessage,
    updateStreamingMessage,
    setStreamingMessageText,
    finishStreamingMessage,
  };
}
