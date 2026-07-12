/**
 * debounce.js — Lightweight debounce and throttle utilities.
 *
 * Debounce delays execution of a function until after `wait` ms have elapsed
 * since the last call. Throttle ensures a function is called at most once per
 * `wait` ms interval.
 *
 * Used for search inputs, resize handlers, and scroll listeners across the UI.
 */

/**
 * Returns a debounced version of `fn` that delays invocation by `wait` ms.
 * @param {Function} fn - The function to debounce.
 * @param {number} wait - Delay in milliseconds.
 * @param {{ leading?: boolean }} [options]
 * @returns {Function}
 */
export function debounce(fn, wait = 300, { leading = false } = {}) {
  let timeoutId = null;

  function debounced(...args) {
    const callNow = leading && timeoutId === null;
    clearTimeout(timeoutId);

    timeoutId = setTimeout(() => {
      timeoutId = null;
      if (!leading) fn.apply(this, args);
    }, wait);

    if (callNow) fn.apply(this, args);
  }

  debounced.cancel = () => {
    clearTimeout(timeoutId);
    timeoutId = null;
  };

  return debounced;
}

/**
 * Returns a throttled version of `fn` that fires at most once per `wait` ms.
 * @param {Function} fn - The function to throttle.
 * @param {number} wait - Interval in milliseconds.
 * @returns {Function}
 */
export function throttle(fn, wait = 300) {
  let lastCall = 0;
  let timeoutId = null;

  return function throttled(...args) {
    const now = Date.now();
    const remaining = wait - (now - lastCall);

    if (remaining <= 0) {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      lastCall = now;
      fn.apply(this, args);
    } else {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        lastCall = Date.now();
        timeoutId = null;
        fn.apply(this, args);
      }, remaining);
    }
  };
}
