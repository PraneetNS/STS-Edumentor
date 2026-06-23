/**
 * SpeakingText — Streams words in real-time as the assistant speaks.
 *
 * Shows the full generated text immediately, highlighting spoken words
 * and the active word as the audio plays.
 */
import React, { memo, useMemo } from 'react';
import { cleanXmlTags } from './MarkdownViewer';

export const SpeakingText = memo(function SpeakingText({
  text = '',
  currentWordIndex = -1,
  isSpeakingTextSync = true,
  isStreaming = false,
}) {
  const cleanedText = useMemo(() => cleanXmlTags(text), [text]);

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
        style={{ display: 'inline', color: '#18181B', overflowWrap: 'break-word', wordBreak: 'normal' }}
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
                  ? 'text-indigo-600 font-semibold bg-indigo-50/80 px-0.5 rounded shadow-sm'
                  : isSpoken
                  ? 'text-zinc-900 font-medium'
                  : 'text-zinc-400'
              }`}
              style={{ display: 'inline' }}
            >
              {word}{idx < words.length - 1 ? ' ' : ''}
            </span>
          );
        })}
        {isStreaming && <span className="stream-cursor" />}
      </span>
    );
  }

  // Otherwise, render full text normally
  return (
    <span className="leading-relaxed" style={{ color: '#18181B', overflowWrap: 'break-word', wordBreak: 'normal' }}>
      {cleanedText}
      {isStreaming && <span className="stream-cursor" />}
    </span>
  );
});

