import { createStore } from './createStore';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export const authStore = createStore((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  profileStats: null,
  _refreshPromise: null,

  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setToken: (token) => set({ token }),
  setIsLoading: (isLoading) => set({ isLoading }),

  register: async (email, password, displayName) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, display_name: displayName })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Registration failed');
    }
    return await res.json();
  },

  login: async (email, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    set({
      user: data.user,
      token: data.access_token,
      isAuthenticated: true
    });
    return data.user;
  },

  logout: async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
    } catch (e) {
      console.error('Logout request failed:', e);
    }
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      profileStats: null
    });
  },

  silentRefresh: async () => {
    // If a refresh request is already in progress, reuse its promise to avoid duplicate network calls.
    if (get()._refreshPromise) {
      return get()._refreshPromise;
    }

    const promise = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          const jwtPayload = JSON.parse(atob(data.access_token.split('.')[1]));
          set({
            token: data.access_token,
            user: {
              user_id: jwtPayload.user_id,
              email: jwtPayload.email,
              display_name: get().user?.display_name || jwtPayload.email.split('@')[0],
              avatar_url: get().user?.avatar_url || null
            },
            isAuthenticated: true
          });
          return true;
        }
      } catch (e) {
        console.error('Silent refresh failed:', e);
      } finally {
        // Clear the in-progress promise once done
        set({ _refreshPromise: null });
      }
      return false;
    })();

    set({ _refreshPromise: promise });
    return promise;
  },

  fetchStats: async () => {
    const token = get().token;
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/profile/stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        set({ profileStats: data });
        return data;
      }
    } catch (e) {
      console.error('Failed to fetch profile stats:', e);
    }
  },

  checkAuth: async () => {
    set({ isLoading: true });
    const success = await get().silentRefresh();
    set({ isLoading: false });
    return success;
  }
}));
