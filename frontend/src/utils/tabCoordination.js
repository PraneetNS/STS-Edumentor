/**
 * tabCoordination — BroadcastChannel-based multi-tab session detection.
 *
 * Problem: if the same session is open in two browser tabs, both will try to
 * hold a WebSocket connection. This causes:
 *   - Doubled rate-limit consumption
 *   - Split/confused conversation state
 *   - Potential audio playback in both tabs simultaneously
 *
 * Solution: the first tab to announce itself becomes the "primary" tab and
 * holds the live WebSocket. Any subsequent tab with the same session ID
 * receives a 'duplicate' notification and shows a warning banner instead of
 * silently fighting for the connection.
 *
 * Design notes:
 *   - BroadcastChannel is same-origin only — no cross-site leakage.
 *   - TAB_ID is a per-page-load UUID; it never persists across refreshes.
 *   - No hard block — we show a banner and disable voice, but the tab
 *     remains usable for reading conversation history.
 *   - If the primary tab is closed, the secondary tab does NOT auto-promote
 *     (the user can simply refresh to get a clean primary connection).
 */

const CHANNEL_NAME = 'edumentor-session';

// Unique identifier for this browser tab / page load.
const TAB_ID = crypto.randomUUID();

let _channel = null;
let _currentSessionId = null;
let _isDuplicate = false;
let _onDuplicateCallback = null;

/**
 * Returns true if BroadcastChannel is available in this browser.
 * It's widely supported (Chrome, Firefox, Edge, Safari 15.4+) but guard
 * anyway so the rest of the app degrades gracefully on older browsers.
 */
function isSupported() {
  return typeof BroadcastChannel !== 'undefined';
}

function getChannel() {
  if (!_channel && isSupported()) {
    _channel = new BroadcastChannel(CHANNEL_NAME);

    _channel.onmessage = (event) => {
      const { type, sessionId, tabId } = event.data ?? {};

      // Ignore messages from our own tab.
      if (tabId === TAB_ID) return;

      if (type === 'announce' && sessionId === _currentSessionId) {
        // Another tab just announced the same session — we are the duplicate.
        _isDuplicate = true;
        if (_onDuplicateCallback) {
          _onDuplicateCallback();
        }
      }

      if (type === 'query' && sessionId === _currentSessionId) {
        // A new tab is asking if anyone already has this session — reply.
        _channel.postMessage({ type: 'announce', sessionId: _currentSessionId, tabId: TAB_ID });
      }
    };
  }
  return _channel;
}

/**
 * Register a callback that fires if a duplicate tab is detected.
 * Call this once, early in app startup (e.g. inside useVoicePipeline).
 *
 * @param {string} sessionId  - The active conversation / session ID.
 * @param {() => void} onDuplicate - Called when another tab with the same
 *                                   sessionId is detected.
 */
export function registerSession(sessionId, onDuplicate) {
  if (!isSupported()) return;

  _currentSessionId = sessionId;
  _isDuplicate = false;
  _onDuplicateCallback = onDuplicate;

  const ch = getChannel();
  if (!ch) return;

  // Query: ask existing tabs if they already hold this session.
  ch.postMessage({ type: 'query', sessionId, tabId: TAB_ID });

  // After a short round-trip window, announce our own presence so any
  // tabs that open *after* us will detect us.
  setTimeout(() => {
    ch.postMessage({ type: 'announce', sessionId, tabId: TAB_ID });
  }, 300);
}

/**
 * Unregister the current session (call on component unmount / session change).
 */
export function unregisterSession() {
  _currentSessionId = null;
  _isDuplicate = false;
  _onDuplicateCallback = null;
}

/**
 * Returns true if this tab has been identified as a duplicate.
 */
export function isDuplicateTab() {
  return _isDuplicate;
}
