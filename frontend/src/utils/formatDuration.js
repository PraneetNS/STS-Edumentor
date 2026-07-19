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
  const secs = Number(totalSeconds) || 0; // Ensure fallback to 0 if NaN or empty
  if (Number.isNaN(secs) || !Number.isFinite(secs) || secs <= 0) {
    return '0s';
  }

  // Calculate standard time components for formatting
  const hours = Math.floor(secs / 3600);
  const minutes = Math.floor((secs % 3600) / 60);
  const seconds = Math.floor(secs % 60);

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

/**
 * Convert a raw number of minutes into a compact readable string.
 * @param {number} totalMinutes
 * @returns {string} e.g. "1h 30m", "45m", "0m"
 */
export function formatMinutes(totalMinutes) {
  const mins = Math.round(Number(totalMinutes));
  if (Number.isNaN(mins) || mins <= 0) return '0m';
  const hours = Math.floor(mins / 60);
  const remaining = mins % 60;
  if (hours > 0) return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
  return `${remaining}m`;
}

/**
 * Format the remaining time until a future timestamp as a countdown string.
 * @param {string|Date|number} futureTimestamp
 * @returns {string} e.g. "2h 15m left", "45m left", or "Expired"
 */
export function formatCountdown(futureTimestamp) {
  const target = new Date(futureTimestamp).getTime();
  const now = Date.now();
  const remainingMs = target - now;

  if (remainingMs <= 0) return 'Expired';
  const remainingSeconds = Math.floor(remainingMs / 1000);
  return `${formatSeconds(remainingSeconds)} left`;
}
