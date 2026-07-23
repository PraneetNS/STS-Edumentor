import React from 'react';
import { MessageSquare, Clock, Zap, Cpu } from 'lucide-react';

/**
 * SessionSummaryCard
 * Displays a detailed card summary for a specific voice session.
 */
export function SessionSummaryCard({ session }) {
  if (!session) return null;

  const {
    title = 'Voice Session',
    created_at,
    turns = 0,
    intents = [],
    tokens_in = 0,
    tokens_out = 0,
    avg_latency_ms = 0,
  } = session;

  const dateFormatted = created_at
    ? new Date(created_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'Recent';

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-color)] p-4 rounded-xl shadow-xs hover:border-[var(--accent-indigo)] transition-all">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-[var(--accent-indigo)]" />
          <h4 className="font-sans font-semibold text-sm text-[var(--text-primary)] truncate max-w-[220px]">
            {title}
          </h4>
        </div>
        <span className="text-[10px] font-mono text-[var(--text-muted)] opacity-70">
          {dateFormatted}
        </span>
      </div>

      <div className="flex items-center gap-3 mt-3 text-xs text-[var(--text-secondary)] font-mono">
        <div className="flex items-center gap-1">
          <Clock size={12} className="opacity-60" />
          <span>{turns} turns</span>
        </div>
        {avg_latency_ms > 0 && (
          <div className="flex items-center gap-1">
            <Zap size={12} className="opacity-60 text-amber-500" />
            <span>{avg_latency_ms}ms avg</span>
          </div>
        )}
        {(tokens_in > 0 || tokens_out > 0) && (
          <div className="flex items-center gap-1">
            <Cpu size={12} className="opacity-60 text-indigo-500" />
            <span>{tokens_in + tokens_out} tokens</span>
          </div>
        )}
      </div>

      {intents.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {intents.map((intent, idx) => (
            <span
              key={idx}
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-[var(--badge-bg)] text-[var(--accent-indigo)] font-medium"
            >
              {intent}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
