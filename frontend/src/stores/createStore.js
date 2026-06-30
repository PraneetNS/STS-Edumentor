import { useState, useEffect } from 'react';

/**
 * createStore - A simple, lightweight, reactive store creator (similar to Zustand).
 * Provides immutable state updates, state selection, and listener tracking.
 */
export function createStore(initialStateCreator) {
  let state;
  const listeners = new Set();

  const getState = () => state;

  const setState = (nextStateOrUpdater) => {
    const nextState = typeof nextStateOrUpdater === 'function'
      ? nextStateOrUpdater(state)
      : nextStateOrUpdater;

    if (nextState !== state) {
      state = { ...state, ...nextState };
      listeners.forEach((listener) => listener(state));
    }
  };

  const subscribe = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };

  state = initialStateCreator(setState, getState);

  const useStore = (selector = (s) => s) => {
    const [selectedValue, setSelectedValue] = useState(() => selector(state));

    useEffect(() => {
      const unsubscribe = subscribe((newState) => {
        setSelectedValue(selector(newState));
      });
      return unsubscribe;
    }, [selector]);

    return selectedValue;
  };

  return {
    getState,
    setState,
    subscribe,
    useStore,
  };
}
