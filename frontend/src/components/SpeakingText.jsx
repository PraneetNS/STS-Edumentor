/**
 * SpeakingText — Streams words in real-time as the assistant speaks.
 *
 * Shows the full generated text immediately, highlighting spoken words
 * and the active word as the audio plays.
 */
import React, { memo, useMemo } from 'react';
import { sanitizeAssistantText } from '../utils/sanitizeAssistantText';
import { ThinkingIndicator } from './ThinkingIndicator';

export const SpeakingText = memo(function SpeakingText({
  text = '',
  currentWordIndex = -1,
  isSpeakingTextSync = true,
  isStreaming = false,
}) {
  const cleanedText = useMemo(() => sanitizeAssistantText(text), [text]);

  // Split text into words, preserving spaces
  const words = useMemo(() => {
    if (!cleanedText) return [];
    // Replace newlines and bullet points/dashes with spaces for spoken word alignment
    const spaces = cleanedText.replace(/[\r\n\-]+/g, ' ');
    return spaces.split(' ').filter(Boolean);
  }, [cleanedText]);

  if (isSpeakingTextSync) {
    return (
      <span
        className="speaking-text-container leading-relaxed"
        style={{ display: 'inline', color: 'var(--text-primary)', overflowWrap: 'break-word', wordBreak: 'normal' }}
      >
        {words.map((word, idx) => {
          // Determine word highlighting state:
          // - active (currently spoken word) gets indigo-600 background highlights
          // - spoken (already read) gets standard dark zinc color
          // - unspoken (future text) stays muted zinc-400
          const isSpoken = idx <= currentWordIndex;
          const isActive = idx === currentWordIndex;

          return (
            <span
              key={idx}
              className={`transition-all duration-150 ${
                isActive
                  ? 'text-[var(--accent-indigo)] font-bold bg-[var(--accent-indigo-glow)] px-1.5 py-0.5 rounded shadow-xs'
                  : isSpoken
                  ? 'text-[var(--text-primary)] font-medium'
                  : 'text-[var(--text-muted)]'
              }`}
              style={{ display: 'inline' }}
            >
              {word}{idx < words.length - 1 ? ' ' : ''}
            </span>
          );
        })}
        {isStreaming && words.length === 0 && <ThinkingIndicator />}
      </span>
    );
  }

  // Otherwise, render full text normally
  return (
    <span className="leading-relaxed" style={{ color: 'var(--text-primary)', overflowWrap: 'break-word', wordBreak: 'normal' }}>
      {cleanedText}
      {isStreaming && !cleanedText && <ThinkingIndicator />}
    </span>
  );
});

