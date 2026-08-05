import { createStore } from './createStore';
import { isJailbreakAttempt } from '../utils/isJailbreakAttempt';
import { authStore } from './authStore';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const STORAGE_KEY = 'edumentor_v3_conversations';

function generateId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
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

  selectConversation: async (id) => {
    set({ activeId: id });

    const token = authStore.getState().token;
    if (!token) return;

    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
    if (!isUuid) return;

    try {
      const res = await fetch(`${API_BASE}/api/sessions/${id}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const fetchedMessages = await res.json();
        set((state) => {
          const updated = state.conversations.map((conv) => {
            if (conv.id !== id) return conv;
            return { ...conv, messages: fetchedMessages };
          });
          saveToStorage(updated);
          return { conversations: updated };
        });
      }
    } catch (e) {
      console.error(`Failed to fetch messages for session ${id}:`, e);
    }
  },

  fetchSessionsFromDb: async () => {
    const token = authStore.getState().token;
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/sessions?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const sessions = await res.json();
        set((state) => {
          const dbConvs = sessions.map(s => {
            const existing = state.conversations.find(c => c.id === s.session_id);
            return {
              id: s.session_id,
              title: s.title || 'Voice Session',
              createdAt: s.created_at || new Date().toISOString(),
              messages: existing ? existing.messages : []
            };
          });

          const merged = [...dbConvs];
          for (const local of state.conversations) {
            if (!merged.some(c => c.id === local.id)) {
              merged.push(local);
            }
          }

          merged.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

          let nextActiveId = state.activeId;
          if (merged.length > 0) {
            const currentActive = state.conversations.find(c => c.id === nextActiveId);
            const hasNoRealMessages = !nextActiveId || !currentActive || currentActive.messages?.length === 0;
            const activeSessionExists = merged.some(c => c.id === nextActiveId);
            if (hasNoRealMessages || !activeSessionExists) {
              nextActiveId = merged[0].id;
            }
          }

          saveToStorage(merged);
          return { conversations: merged, activeId: nextActiveId };
        });
      }
    } catch (e) {
      console.error('Failed to fetch sessions from db:', e);
    }
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
