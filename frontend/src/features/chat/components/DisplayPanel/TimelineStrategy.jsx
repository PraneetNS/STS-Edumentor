import React from 'react';
import { Target, Zap, Circle } from 'lucide-react';

export function TimelineStrategy({ block }) {
  // Parse lines representing steps
  const items = block.content
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'))
    .map((line) => line.replace(/^[-*+]\s*/, '').replace(/^\d+\.\s*/, ''));

  return (
    <div className="flex flex-col gap-6 p-6 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg shadow-sm">
      <div className="flex flex-col gap-1 select-none">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 uppercase tracking-wider text-xs">
          {block.title || 'Roadmap Path'}
        </h3>
        <p className="text-xs text-zinc-500">
          Sequential execution path.
        </p>
      </div>

      <div className="relative pl-6 border-l border-zinc-200 dark:border-zinc-800 ml-3 flex flex-col gap-6">
        {items.map((item, idx) => {
          const isFirst = idx === 0;
          const isLast = idx === items.length - 1;

          return (
            <div key={idx} className="relative flex flex-col gap-1 text-zinc-700 dark:text-zinc-300">
              {/* Dot indicator */}
              <div
                className={`absolute -left-[31px] top-1.5 w-4 h-4 rounded-full border-2 bg-white dark:bg-zinc-900 flex items-center justify-center ${
                  isFirst
                    ? 'border-indigo-500 text-indigo-500 ring-4 ring-indigo-50/50 dark:ring-indigo-950/20'
                    : isLast
                    ? 'border-emerald-500 text-emerald-500'
                    : 'border-zinc-400 text-zinc-400'
                }`}
              >
                <div
                  className={`w-1.5 h-1.5 rounded-full ${
                    isFirst ? 'bg-indigo-500' : isLast ? 'bg-emerald-500' : 'bg-zinc-400'
                  }`}
                />
              </div>

              {/* Title & Index */}
              <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                Step {idx + 1}
              </span>
              <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 leading-snug">
                {item.split(':')[0]}
              </p>
              {item.includes(':') && (
                <p className="text-xs text-zinc-500 leading-relaxed font-normal">
                  {item.substring(item.indexOf(':') + 1).trim()}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
