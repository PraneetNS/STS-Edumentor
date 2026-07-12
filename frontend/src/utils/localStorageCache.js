/**
 * localStorageCache.js — Safe localStorage wrapper with TTL support.
 *
 * Wraps localStorage get/set with JSON serialization, expiry (TTL),
 * and graceful fallback for environments where localStorage is unavailable
 * (e.g., private/incognito mode, SSR).
 *
 * Used by stores and hooks that need lightweight client-side persistence.
 */

const PREFIX = 'edumentor_';

/**
 * Write a value to localStorage with an optional TTL.
 * @param {string} key
 * @param {*} value - Must be JSON-serializable.
 * @param {number} [ttlMs] - Time to live in milliseconds. Omit for no expiry.
 */
export function cacheSet(key, value, ttlMs) {
  try {
    const entry = {
      value,
      expiry: ttlMs ? Date.now() + ttlMs : null,
    };
    localStorage.setItem(PREFIX + key, JSON.stringify(entry));
  } catch {
    // Storage quota exceeded or unavailable — fail silently.
  }
}

/**
 * Read a cached value from localStorage.
 * Returns `null` if missing or expired.
 * @param {string} key
 * @returns {*|null}
 */
export function cacheGet(key) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;

    const entry = JSON.parse(raw);
    if (entry.expiry && Date.now() > entry.expiry) {
      localStorage.removeItem(PREFIX + key);
      return null;
    }
    return entry.value;
  } catch {
    return null;
  }
}

/**
 * Remove a specific cached entry.
 * @param {string} key
 */
export function cacheRemove(key) {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    // Ignore.
  }
}

/**
 * Clear all EduMentor-prefixed keys from localStorage.
 */
export function cacheClear() {
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(PREFIX)) keysToRemove.push(k);
    }
    keysToRemove.forEach(k => localStorage.removeItem(k));
  } catch {
    // Ignore.
  }
}
