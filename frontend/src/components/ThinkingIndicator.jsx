import React, { memo } from 'react';

/**
 * ThinkingIndicator — "Thinking" label with three waving dots.
 * Shown while the assistant is generating a response (before visible text arrives).
 */
export const ThinkingIndicator = memo(function ThinkingIndicator({ className = '' }) {
  return (
    <span className={`thinking-indicator ${className}`.trim()} aria-label="Thinking" role="status">
      <span className="thinking-indicator-label">Thinking</span>
      <span className="thinking-indicator-dots" aria-hidden="true">
        <span className="thinking-dot dot-1" />
        <span className="thinking-dot dot-2" />
        <span className="thinking-dot dot-3" />
      </span>
    </span>
  );
});
