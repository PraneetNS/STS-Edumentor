import React from 'react';
import { Tooltip } from '../Common/Tooltip';

export function Heatmap({ data = [] }) {
  // Generate mock days if data is empty
  const getIntensityColor = (count) => {
    if (!count || count === 0) return 'bg-[#FAF8F2] border-black/10';
    if (count <= 2) return 'bg-[var(--lavender)]/50 border-black/40';
    if (count <= 5) return 'bg-[var(--lavender)] border-black/70';
    if (count <= 8) return 'bg-[var(--mint)] border-black';
    return 'bg-[var(--yellow)] border-black';
  };

  // Group by day of week
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  
  // Arrange grid in 4 weeks (4 cols) x 7 days (7 rows)
  const grid = Array.from({ length: 7 }, (_, dayIdx) => {
    return Array.from({ length: 4 }, (_, weekIdx) => {
      const dataIdx = weekIdx * 7 + dayIdx;
      return data[dataIdx] || { date: '', count: 0 };
    });
  });

  return (
    <div className="flex flex-col gap-2 select-none w-full">
      <div className="flex justify-between items-center font-mono text-[9px] uppercase text-black/50 mb-2">
        <span>Activity Grid (Past 4 Weeks)</span>
        <div className="flex items-center gap-1">
          <span>Less</span>
          <div className="w-2.5 h-2.5 bg-[#FAF8F2] border border-black/20 rounded-sm" />
          <div className="w-2.5 h-2.5 bg-[var(--lavender)]/50 border border-black/40 rounded-sm" />
          <div className="w-2.5 h-2.5 bg-[var(--lavender)] border border-black/60 rounded-sm" />
          <div className="w-2.5 h-2.5 bg-[var(--mint)] border border-black rounded-sm" />
          <div className="w-2.5 h-2.5 bg-[var(--yellow)] border border-black rounded-sm" />
          <span>More</span>
        </div>
      </div>

      <div className="flex gap-2">
        {/* Days label */}
        <div className="flex flex-col justify-between font-mono text-[8px] uppercase text-black/40 py-1 flex-shrink-0">
          {days.map(d => <span key={d}>{d}</span>)}
        </div>

        {/* Heatmap Grid */}
        <div className="grid grid-cols-4 gap-1.5 flex-1">
          {Array.from({ length: 4 }).map((_, weekIdx) => (
            <div key={weekIdx} className="flex flex-col gap-1.5">
              {Array.from({ length: 7 }).map((_, dayIdx) => {
                const item = data[weekIdx * 7 + dayIdx] || { date: 'No Study', count: 0 };
                const tipText = `${item.date || 'Rest Day'}: ${item.count} interaction turns`;
                
                return (
                  <Tooltip key={dayIdx} text={tipText}>
                    <div 
                      className={`w-full aspect-square border-2 rounded-sm transition-all hover:scale-110 hover:border-black cursor-pointer ${getIntensityColor(item.count)}`}
                    />
                  </Tooltip>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
