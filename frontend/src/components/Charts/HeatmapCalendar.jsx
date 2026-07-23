import React from 'react';

/**
 * HeatmapCalendar
 * Renders a GitHub-style 90-day activity contribution grid.
 * Accepts `data`: list of { date: 'YYYY-MM-DD', count: number, sessions: number }
 */
export function HeatmapCalendar({ data = [], days = 90 }) {
  // Map data by YYYY-MM-DD string
  const countsByDate = React.useMemo(() => {
    const map = new Map();
    (data || []).forEach(item => {
      if (item.date) {
        map.set(item.date, item.count || item.sessions || 0);
      }
    });
    return map;
  }, [data]);

  // Generate grid cells for the last N days
  const cells = React.useMemo(() => {
    const list = [];
    const today = new Date();
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const iso = d.toISOString().split('T')[0];
      const count = countsByDate.get(iso) || 0;
      list.push({ date: iso, count, dayOfWeek: d.getDay() });
    }
    return list;
  }, [days, countsByDate]);

  function getIntensityClass(count) {
    if (count === 0) return 'bg-[var(--bg-secondary)] border-[var(--border-color)] opacity-40';
    if (count <= 2) return 'bg-emerald-200 dark:bg-emerald-950 border-emerald-300 dark:border-emerald-800';
    if (count <= 5) return 'bg-emerald-400 dark:bg-emerald-700 border-emerald-500';
    if (count <= 10) return 'bg-emerald-600 dark:bg-emerald-500 text-white';
    return 'bg-emerald-700 dark:bg-emerald-400 text-white';
  }

  const totalActivity = cells.reduce((acc, c) => acc + c.count, 0);

  return (
    <div className="flex flex-col gap-3 p-4 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl">
      <div className="flex items-center justify-between font-mono text-xs">
        <span className="font-semibold text-[var(--text-primary)]">
          Activity Heatmap ({days} Days)
        </span>
        <span className="text-[var(--text-muted)]">
          {totalActivity} total turn{totalActivity !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="flex gap-1 overflow-x-auto py-1 scrollbar-none">
        <div className="grid grid-rows-7 grid-flow-col gap-1.5">
          {cells.map((cell, idx) => (
            <div
              key={idx}
              title={`${cell.date}: ${cell.count} interactions`}
              className={`w-3 h-3 rounded-xs border transition-all duration-150 cursor-pointer hover:scale-125 ${getIntensityClass(
                cell.count
              )}`}
            />
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] font-mono text-[var(--text-muted)] pt-1 border-t border-[var(--border-color)]">
        <span>Less</span>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-xs bg-[var(--bg-secondary)] border border-[var(--border-color)] opacity-40" />
          <div className="w-2.5 h-2.5 rounded-xs bg-emerald-200 dark:bg-emerald-950" />
          <div className="w-2.5 h-2.5 rounded-xs bg-emerald-400 dark:bg-emerald-700" />
          <div className="w-2.5 h-2.5 rounded-xs bg-emerald-600 dark:bg-emerald-500" />
          <div className="w-2.5 h-2.5 rounded-xs bg-emerald-700 dark:bg-emerald-400" />
        </div>
        <span>More</span>
      </div>
    </div>
  );
}
