import { createStore } from './createStore';
import { isJailbreakAttempt } from '../utils/isJailbreakAttempt';
import { authStore } from './authStore';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const BASE_STORAGE_KEY = 'edumentor_v3_conversations';

// Return a per-user storage key, falling back to the base key for
// unauthenticated / guest sessions so we never mix two users' caches.
function storageKey() {
  try {
    const raw = localStorage.getItem('edumentor_user');
    if (raw) {
      const user = JSON.parse(raw);
      if (user?.user_id) return `${BASE_STORAGE_KEY}:${user.user_id}`;
    }
  } catch (_) {}
  return BASE_STORAGE_KEY;
}

function generateId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// One-time migration: if the user-scoped key is empty but the legacy
// generic key has data, move that data to the scoped key and wipe the old one.
function migrateFromLegacyKey() {
  const scoped = storageKey();
  if (scoped === BASE_STORAGE_KEY) return null; // already on legacy / guest path
  try {
    const alreadyMigrated = localStorage.getItem(scoped);
    let isNewOrEmpty = false;
    if (alreadyMigrated) {
      try {
        const parsedScoped = JSON.parse(alreadyMigrated);
        if (
          !Array.isArray(parsedScoped) ||
          parsedScoped.length === 0 ||
          (parsedScoped.length === 1 && (!parsedScoped[0].messages || parsedScoped[0].messages.length === 0))
        ) {
          isNewOrEmpty = true;
        }
      } catch (_) {}
    } else {
      isNewOrEmpty = true;
    }

    if (!isNewOrEmpty) return null; // scoped key has actual user conversations, don't overwrite

    const legacy = localStorage.getItem(BASE_STORAGE_KEY);
    if (!legacy) return null;
    const parsed = JSON.parse(legacy);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    // Write into scoped key and remove the old generic one.
    localStorage.setItem(scoped, legacy);
    localStorage.removeItem(BASE_STORAGE_KEY);
    console.info('[Store] Migrated legacy conversations to scoped key:', scoped);
    return parsed;
  } catch (e) {
    console.warn('[Store] Migration failed:', e);
  }
  return null;
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(storageKey());
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) {
    console.warn('[Store] Failed to load conversations:', e);
  }
  // Attempt legacy migration before giving up.
  return migrateFromLegacyKey();
}

function saveToStorage(convs) {
  try {
    localStorage.setItem(storageKey(), JSON.stringify(convs));
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
  pausedThreads: [],

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

  fetchSessionsFromDb: async (explicitToken) => {
    const token = explicitToken || authStore.getState().token;
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
    });
  },

  removeMessage: (msgId) => {
    set((state) => {
      const updated = state.conversations.map((conv) => {
        if (conv.id !== state.activeId) return conv;
        const msgs = conv.messages.filter((m) => m.id !== msgId);
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

  fetchPausedThreads: async (sessionId) => {
    const token = authStore.getState().token;
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/paused_threads`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const threads = await res.json();
        set({ pausedThreads: threads });
      }
    } catch (e) {
      console.error(`Failed to fetch paused threads for session ${sessionId}:`, e);
    }
  },

  addPausedThread: (thread) => {
    set((state) => {
      const exists = state.pausedThreads.some(t => t.thread_id === thread.thread_id);
      if (exists) {
        return {
          pausedThreads: state.pausedThreads.map(t => t.thread_id === thread.thread_id ? { ...t, ...thread } : t)
        };
      }
      return { pausedThreads: [...state.pausedThreads, thread] };
    });
  },

  removePausedThread: (threadId) => {
    set((state) => ({
      pausedThreads: state.pausedThreads.filter(t => t.thread_id !== threadId)
    }));
  },

  // ── Called on LOGOUT ──────────────────────────────────────────────────────
  // Blanks the in-memory store so the UI shows nothing after sign-out,
  // but intentionally does NOT touch localStorage so the user's scoped key
  // survives — meaning the same account's history is restored on next login.
  resetInMemory: () => {
    const fresh = createNewConversation();
    set({
      conversations: [fresh],
      activeId: fresh.id,
      pausedThreads: []
    });
  },

  // ── Called when we genuinely want to erase a user's history ───────────────
  clearConversations: () => {
    localStorage.removeItem(storageKey());
    const fresh = createNewConversation();
    set({
      conversations: [fresh],
      activeId: fresh.id,
      pausedThreads: []
    });
  },

  // ── Called right after login ───────────────────────────────────────────────
  // 1. Immediately restore from localStorage (instant, no network).
  // 2. Then fetch fresh sessions from the DB and merge on top so the user
  //    always sees their full, authoritative history — even if localStorage
  //    was stale or the account was used on another device.
  reloadFromStorage: (explicitToken) => {
    const saved = loadFromStorage();
    if (saved && saved.length > 0) {
      set({ conversations: saved, activeId: saved[0].id });
    } else {
      const fresh = createNewConversation();
      set({ conversations: [fresh], activeId: fresh.id });
    }
    // Fire DB sync in the background (non-blocking).
    get().fetchSessionsFromDb(explicitToken).catch(() => {});
  },
}));
