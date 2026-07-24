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
    <div className="bg-[var(--bg-primary)]/85 backdrop-blur-sm border border-[var(--border-default)]/60 p-4.5 rounded-2xl shadow-[0_4px_15px_rgb(0,0,0,0.01)] hover:border-indigo-400/50 hover:shadow-[0_8px_25px_rgb(0,0,0,0.02)] transition-all select-none">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-indigo-400" />
          <h4 className="font-sans font-bold text-xs.5 text-[var(--text-primary)] truncate max-w-[220px]">
            {title}
          </h4>
        </div>
        <span className="text-[10px] font-sans font-semibold text-[var(--text-muted)]">
          {dateFormatted}
        </span>
      </div>

      <div className="flex items-center gap-3 mt-3 text-[11px] text-[var(--text-secondary)] font-sans font-medium">
        <div className="flex items-center gap-1">
          <Clock size={12} className="text-[var(--text-muted)] flex-shrink-0" />
          <span>{turns} turns</span>
        </div>
        {avg_latency_ms > 0 && (
          <div className="flex items-center gap-1">
            <Zap size={12} className="text-amber-400 flex-shrink-0" />
            <span>{avg_latency_ms}ms avg</span>
          </div>
        )}
        {(tokens_in > 0 || tokens_out > 0) && (
          <div className="flex items-center gap-1">
            <Cpu size={12} className="text-indigo-400 flex-shrink-0" />
            <span>{tokens_in + tokens_out} tokens</span>
          </div>
        )}
      </div>

      {intents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {intents.map((intent, idx) => (
            <span
              key={idx}
              className="text-[9.5px] font-sans px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 font-semibold border border-indigo-500/10"
            >
              {intent}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
