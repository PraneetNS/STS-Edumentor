import { useRef, useCallback } from 'react';
import { throttle } from '../utils/debounce';

/**
 * useThrottle — React hook that throttles a callback.
 *
 * Returns a stable, throttled version of the provided function.
 * The throttled function is memoized for the component lifetime;
 * the inner callback ref is updated so stale closure issues are avoided.
 *
 * @param {Function} fn   - The callback to throttle.
 * @param {number}   wait - Throttle interval in milliseconds (default: 300).
 * @returns {Function} Stable throttled callback.
 *
 * @example
 * const handleScroll = useThrottle(() => { doSomething(); }, 100);
 * window.addEventListener('scroll', handleScroll);
 */
export function useThrottle(fn, wait = 300) {
  const fnRef = useRef(fn);
  fnRef.current = fn; // Keep ref in sync without re-creating the throttle

  const throttledRef = useRef(
    throttle((...args) => fnRef.current(...args), wait),
  );

  return useCallback((...args) => throttledRef.current(...args), []);
}
