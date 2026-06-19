/**
 * SpeakingText — Highlights words in real-time as the assistant speaks.
 *
 * Visual states during active sync (isSpeakingTextSync=true):
 *  - Spoken words (index < currentWordIndex): White / Opaque
 *  - Active word (index === currentWordIndex): Accent colored (Indigo/Purple), slightly scaled, text-shadow glow
 *  - Upcoming words (index > currentWordIndex): Grey ghost text (Dimmed, semi-transparent)
 *
 * When not active, renders as a standard flowing text segment (fully white / opaque).
 */
import React, { memo, useMemo } from 'react';
import { motion } from 'framer-motion';

export const SpeakingText = memo(function SpeakingText({
  text = '',
  currentWordIndex = -1,
  isSpeakingTextSync = true,
}) {
  // Split text into words, preserving spaces
  const words = useMemo(() => {
    if (!text) return [];
    return text.split(' ');
  }, [text]);

  if (isSpeakingTextSync) {
    return (
      <span
        className="speaking-text-container leading-relaxed flex flex-wrap gap-x-1"
        style={{ display: 'inline', lineBreak: 'anywhere' }}
      >
        {words.map((word, idx) => {
          const isSpoken = idx < currentWordIndex;
          const isActive = idx === currentWordIndex;

          // Custom style configurations
          let color = 'rgba(255, 255, 255, 0.25)'; // Grey ghost for upcoming words
          let fontWeight = 'normal';
          let scale = 1;
          let textShadow = 'none';

          if (isSpoken) {
            color = 'rgba(255, 255, 255, 0.95)'; // Confirmed white
          } else if (isActive) {
            color = 'var(--accent, #6366f1)'; // Accent color for current word
            fontWeight = '600';
            scale = 1.05;
            textShadow = '0 0 12px rgba(99, 102, 241, 0.4)';
          }

          return (
            <motion.span
              key={`${idx}-${word}`}
              animate={{ color, scale, textShadow }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
              style={{
                display: 'inline-block',
                marginRight: '4px',
                fontWeight,
                transformOrigin: 'bottom center',
              }}
            >
              {word}
            </motion.span>
          );
        })}
      </span>
    );
  }

  // Otherwise, render full text normally
  return (
    <span className="leading-relaxed">
      {text}
    </span>
  );
});
