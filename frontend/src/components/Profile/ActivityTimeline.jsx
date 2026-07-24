import React from 'react';
import { TimelineCard } from '../Cards/TimelineCard';
import { MessageSquare, BookOpen, Zap, Clock } from 'lucide-react';

/**
 * Groups conversations into Today / Yesterday / This Week / Earlier buckets.
 * Each conversation is displayed as a timeline entry.
 */
function groupConversationsByDate(conversations) {
  if (!conversations || conversations.length === 0) return [];

  const now = new Date();
  const todayStr = now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toDateString();

  const groups = {
    Today: [],
    Yesterday: [],
    'This Week': [],
    Earlier: [],
  };

  // Sort newest first
  const sorted = [...conversations].sort((a, b) => {
    const ta = a.createdAt || a.updatedAt || 0;
    const tb = b.createdAt || b.updatedAt || 0;
    return new Date(tb) - new Date(ta);
  });

  sorted.forEach(conv => {
    const ts = conv.createdAt || conv.updatedAt;
    if (!ts) return;
    const d = new Date(ts);
    const dStr = d.toDateString();
    const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));

    let bucket;
    if (dStr === todayStr) bucket = 'Today';
    else if (dStr === yesterdayStr) bucket = 'Yesterday';
    else if (diffDays <= 7) bucket = 'This Week';
    else bucket = 'Earlier';

    groups[bucket].push({
      conv,
      time: dStr === todayStr || dStr === yesterdayStr
        ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : `${diffDays} Days Ago`,
    });
  });

  // Build output array — only include groups that have items
  return ['Today', 'Yesterday', 'This Week', 'Earlier']
    .filter(g => groups[g].length > 0)
    .map(g => ({ group: g, items: groups[g] }));
}

/**
 * Pick an icon based on conversation title content.
 */
function pickIcon(title = '') {
  const t = title.toLowerCase();
  if (t.includes('code') || t.includes('dsa') || t.includes('algorithm') || t.includes('tree') || t.includes('graph')) return Zap;
  if (t.includes('interview') || t.includes('quiz') || t.includes('test')) return Clock;
  if (t.includes('design') || t.includes('system') || t.includes('architect')) return BookOpen;
  return MessageSquare;
}

const COLORS = ['bg-[var(--lavender)]', 'bg-[var(--yellow)]', 'bg-[var(--mint)]', 'bg-[var(--yellow)]'];

export function ActivityTimeline({ conversations = [], sessionHistory = [] }) {
  // Normalize DB session history items to standard timeline object structure
  const normalizedDbSessions = sessionHistory.map(s => ({
    id: s.session_id,
    title: s.title || 'Voice Session',
    createdAt: s.created_at,
    turns: s.turns,
    intents: s.intents,
    isFromDb: true,
  }));

  // Prevent duplication if local conversation shares an ID with DB session
  const dbIds = new Set(normalizedDbSessions.map(s => s.id));
  const uniqueLocal = (conversations || []).filter(c => !dbIds.has(c.id));

  const allSessions = [...normalizedDbSessions, ...uniqueLocal];
  const grouped = groupConversationsByDate(allSessions);

  if (grouped.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 gap-2 text-[var(--text-muted)]">
        <MessageSquare size={28} className="opacity-30" />
        <p className="font-sans text-xs text-center opacity-60">
          No sessions yet. Start a voice conversation to see your activity here.
        </p>
      </div>
    );
  }

  let colorIdx = 0;

  return (
    <div className="flex flex-col gap-6 select-none font-sans">
      {grouped.map((groupObj, idx) => (
        <div key={idx} className="flex flex-col gap-3">
          <h4 className="font-sans font-bold text-[10.5px] uppercase text-[var(--text-muted)] tracking-wider mb-2">
            {groupObj.group}
          </h4>

          <div className="flex flex-col">
            {groupObj.items.map((item, itemIdx) => {
              const isLast =
                idx === grouped.length - 1 &&
                itemIdx === groupObj.items.length - 1;
              const Icon = pickIcon(item.conv.title);
              const colorClass = COLORS[colorIdx % COLORS.length];
              colorIdx++;

              // Build description from turns / message count / intents
              const turnsCount = item.conv.turns || item.conv.messages?.length || 0;
              const intentTag = item.conv.intents?.length
                ? ` • ${item.conv.intents.slice(0, 2).join(', ')}`
                : '';
              const desc = turnsCount > 0
                ? `${turnsCount} turn${turnsCount !== 1 ? 's' : ''}${intentTag}`
                : item.conv.title || 'Voice session';

              return (
                <TimelineCard
                  key={item.conv.id || itemIdx}
                  time={item.time}
                  title={item.conv.title || 'Voice Session'}
                  desc={desc}
                  icon={Icon}
                  colorClass={colorClass}
                  isLast={isLast}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
