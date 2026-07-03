/**
 * formatDuration — Human-readable duration formatter.
 *
 * Converts raw seconds or minutes into a friendly string like:
 *   "2h 15m", "45m", "30s"
 *
 * Used across the analytics dashboard, session history, and status bar.
 */

/**
 * Convert a number of seconds into a compact readable string.
 * @param {number} totalSeconds
 * @returns {string}
 */
export function formatSeconds(totalSeconds) {
  if (!totalSeconds || totalSeconds <= 0) return '0s';

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  if (hours > 0) {
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  if (minutes > 0) {
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  return `${seconds}s`;
}

/**
 * Convert a float number of hours into a compact readable string.
 * @param {number} hours - e.g. 2.5
 * @returns {string}
 */
export function formatHours(hours) {
  if (!hours || hours <= 0) return '0m';
  return formatSeconds(Math.round(hours * 3600));
}

/**
 * Format a session's average response delay with appropriate unit.
 * @param {number} seconds
 * @returns {string} e.g. "1.4s" or "240ms"
 */
export function formatResponseDelay(seconds) {
  if (!seconds || seconds <= 0) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
}

/**
 * Return a human-relative label for a timestamp.
 * @param {string|Date} timestamp
 * @returns {string} "Today", "Yesterday", or "Jun 29"
 */
export function formatRelativeDate(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();

  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
