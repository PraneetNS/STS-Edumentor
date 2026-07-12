import { useState, useEffect, useCallback } from 'react';
import { cacheGet, cacheSet, cacheRemove } from '../utils/localStorageCache';

/**
 * useLocalStorage — React hook for persistent state backed by localStorage.
 *
 * Behaves like useState but reads from and writes to localStorage under the
 * given key. Automatically handles JSON serialisation/deserialisation and
 * falls back gracefully when storage is unavailable.
 *
 * @param {string} key          - localStorage key (will be namespaced automatically).
 * @param {*}      initialValue - Default value when no stored value exists.
 * @param {number} [ttlMs]      - Optional time-to-live in milliseconds.
 * @returns {[*, Function, Function]} [value, setValue, clearValue]
 *
 * @example
 * const [theme, setTheme, clearTheme] = useLocalStorage('theme', 'dark');
 */
export function useLocalStorage(key, initialValue, ttlMs) {
  const [storedValue, setStoredValue] = useState(() => {
    const cached = cacheGet(key);
    return cached !== null ? cached : initialValue;
  });

  const setValue = useCallback(
    (value) => {
      try {
        const next = value instanceof Function ? value(storedValue) : value;
        setStoredValue(next);
        cacheSet(key, next, ttlMs);
      } catch {
        // Ignore write errors (quota exceeded, etc.)
      }
    },
    [key, storedValue, ttlMs],
  );

  const clearValue = useCallback(() => {
    setStoredValue(initialValue);
    cacheRemove(key);
  }, [key, initialValue]);

  // Sync across tabs via storage events
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === `edumentor_${key}`) {
        const cached = cacheGet(key);
        setStoredValue(cached !== null ? cached : initialValue);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [key, initialValue]);

  return [storedValue, setValue, clearValue];
}
