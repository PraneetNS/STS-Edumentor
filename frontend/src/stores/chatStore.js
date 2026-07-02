import { createStore } from './createStore';
import { isJailbreakAttempt } from '../utils/isJailbreakAttempt';

const STORAGE_KEY = 'edumentor_v3_conversations';

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
    id: generateId(),
    title: 'New Conversation',
    createdAt: new Date().toISOString(),
    messages: [],
  };
}

function getInitialConversations() {
  const saved = loadFromStorage();
  if (saved) return saved;
  return [createNewConversation()];
}

const initialConversations = getInitialConversations();

export const chatStore = createStore((set, get) => ({
  conversations: initialConversations,
  activeId: initialConversations[0].id,

  createConversation: () => {
    const newConv = createNewConversation();
    set((state) => {
      const updated = [newConv, ...state.conversations];
      saveToStorage(updated);
      return { conversations: updated, activeId: newConv.id };
    });
    return newConv.id;
  },

  selectConversation: (id) => {
    set({ activeId: id });
  },

  deleteConversation: (id, e) => {
    e?.stopPropagation();
    set((state) => {
      const updated = state.conversations.filter((c) => c.id !== id);
      saveToStorage(updated);

      let nextActiveId = state.activeId;
      if (state.activeId === id) {
        if (updated.length > 0) {
          nextActiveId = updated[0].id;
        } else {
          const fresh = createNewConversation();
          updated.push(fresh);
          saveToStorage(updated);
          nextActiveId = fresh.id;
        }
      }
      return { conversations: updated, activeId: nextActiveId };
    });
  },

  addMessage: (role, text, extra = {}) => {
    if (role === 'user' && isJailbreakAttempt(text)) {
      console.warn('[SECURITY] Blocked jailbreak attempt from being stored:', text?.slice(0, 50));
      return null;
    }

    const msgId = extra.id || (role === 'user' ? 'u-' : 'a-') + Date.now();
    
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = [...conv.messages];
        msgs.push({
          id: msgId,
          role,
          text,
          timestamp: new Date().toISOString(),
          ...extra,
        });

        let title = conv.title;
        if (title === 'New Conversation' && role === 'user' && text) {
          title = text.length > 36 ? text.slice(0, 36) + '…' : text;
        }

        return { ...conv, title, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });

    return msgId;
  },

  updateStreamingMessage: (msgId, textDelta) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.map((m) => {
          if (m.id === msgId) {
            return { ...m, text: m.text + textDelta };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });
  },

  setStreamingMessageText: (msgId, fullText) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.map((m) => {
          if (m.id === msgId) {
            return { ...m, text: fullText };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });
  },

  setStreamingMessageFollowup: (msgId, followup) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.map((m) => {
          if (m.id === msgId) {
            return { ...m, followup };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });
  },

  finishStreamingMessage: (msgId) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.map((m) => {
          if (m.id === msgId) {
            const { isStreaming, ...rest } = m;
            return rest;
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });
  },

  saveMessageSnapshot: (msgId, dataUrl) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.map((m) => {
          if (m.id === msgId) {
            return { ...m, avatarSnapshot: dataUrl };
          }
          return m;
        });
        return { ...conv, messages: msgs };
      });
      saveToStorage(updated);
      return { conversations: updated };
    });
  },
}));
