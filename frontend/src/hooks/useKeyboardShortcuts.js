/**
 * useKeyboardShortcuts — Global keyboard shortcut hook.
 *
 * Registers a map of key combos → handler functions.
 * Cleans up listeners automatically on unmount.
 *
 * Usage:
 *   useKeyboardShortcuts({
 *     'ctrl+k':   () => openSearch(),
 *     'Escape':   () => closeModal(),
 *     '/':        () => focusInput(),
 *   });
 *
 * Supported modifiers: ctrl, shift, alt, meta
 */
import { useEffect } from 'react';

/**
 * Normalize a key combo string → lowercase canonical form.
 * e.g. "Ctrl+K" → "ctrl+k", "Escape" → "escape"
 */
function normalizeCombo(combo) {
  return combo
    .split('+')
    .map((p) => p.trim().toLowerCase())
    .join('+');
}

/**
 * Build a canonical key combo string from a KeyboardEvent.
 * @param {KeyboardEvent} e
 * @returns {string}
 */
function getComboFromEvent(e) {
  const parts = [];
  if (e.ctrlKey)  parts.push('ctrl');
  if (e.altKey)   parts.push('alt');
  if (e.shiftKey) parts.push('shift');
  if (e.metaKey)  parts.push('meta');

  // Avoid double-adding modifier keys themselves
  const key = e.key.toLowerCase();
  const isModifier = ['control', 'alt', 'shift', 'meta'].includes(key);
  if (!isModifier) parts.push(key);

  return parts.join('+');
}

/**
 * @param {Record<string, (e: KeyboardEvent) => void>} shortcuts
 *   Map of key combo → handler. Combos are case-insensitive.
 * @param {boolean} [enabled=true]
 *   Set to false to temporarily disable all shortcuts (e.g. during recording).
 */
export function useKeyboardShortcuts(shortcuts, enabled = true) {
  useEffect(() => {
    if (!enabled) return;

    // Pre-normalize all keys once
    const normalizedMap = {};
    for (const [combo, handler] of Object.entries(shortcuts)) {
      normalizedMap[normalizeCombo(combo)] = handler;
    }

    const handleKeyDown = (e) => {
      // Don't fire inside text inputs to avoid hijacking typing
      const target = e.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target.isContentEditable;

      const combo = getComboFromEvent(e);

      // Allow Escape even during typing
      if (isTyping && combo !== 'escape') return;

      const handler = normalizedMap[combo];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts, enabled]);
}
