import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Trophy, Zap, Target } from 'lucide-react';

/**
 * ContextCards — Small floating learning context cards placed near the avatar.
 * Generates dynamic context based on recent conversation text.
 */
export function ContextCards({ messages = [] }) {
  // FIX 6 — Guard: null/undefined messages → show skeleton cards instead of crash
  if (!messages) {
    return (
      <div className="context-cards" aria-label="Loading context">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="context-card"
            style={{ opacity: 0.4, minWidth: '80px', height: '28px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-full)' }}
            aria-hidden="true"
          />
        ))}
      </div>
    );
  }

  // Simple heuristic for learning context based on recent messages
  const getContext = () => {
    if (messages.length === 0) {
      return [
        { id: 'start', icon: Target, label: 'Ready', text: 'Waiting for topic...' }
      ];
    }

    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    // FIX 6 — guard: lastUserMsg.text may be undefined during streaming
    const text = lastUserMsg?.text ? lastUserMsg.text.toLowerCase() : '';
    
    const cards = [];
    
    // Default learning card
    cards.push({ id: 'active', icon: BookOpen, label: 'Active', text: 'Discussion mode' });

    // Try to guess topic
    if (text.includes('react') || text.includes('javascript') || text.includes('code')) {
      cards.push({ id: 'topic-code', icon: Zap, label: 'Topic', text: 'Software Engineering' });
    } else if (text.includes('math') || text.includes('calculus') || text.includes('algebra')) {
      cards.push({ id: 'topic-math', icon: Zap, label: 'Topic', text: 'Mathematics' });
    } else if (text.includes('physics') || text.includes('science')) {
      cards.push({ id: 'topic-sci', icon: Zap, label: 'Topic', text: 'Science' });
    }

    // Add a progress card if conversation is long
    if (messages.length > 6) {
      cards.push({ id: 'progress', icon: Trophy, label: 'Focus', text: 'Deep dive' });
    }

    return cards.slice(0, 3); // Max 3 cards
  };

  const cards = getContext();

  return (
    <div className="context-cards">
      <AnimatePresence>
        {cards.map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.id}
              initial={{ opacity: 0, y: 10, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ delay: i * 0.1, duration: 0.3 }}
              className="context-card"
            >
              <Icon className="context-card-icon" style={{ color: 'var(--accent-indigo)' }} />
              <span className="context-card-label">{card.label}:</span>
              <span>{card.text}</span>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
