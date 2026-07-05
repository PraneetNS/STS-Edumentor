import React from 'react';
import { motion } from 'framer-motion';

/**
 * TimelineCard component to display an event or activity in a vertical timeline list.
 *
 * @param {Object} props
 * @param {string} props.time - The timestamp or period for the timeline event.
 * @param {string} props.title - The title or headline of the timeline card.
 * @param {string} [props.desc] - Optional description text detail.
 * @param {React.ComponentType<{ size: number, className: string }>} [props.icon] - Optional React Lucide/SVG icon component.
 * @param {string} [props.colorClass='bg-white'] - Optional background color class for the icon wrapper.
 * @param {boolean} [props.isLast=false] - If true, hides the vertical connecting line below the node.
 * @param {string} [props.className=''] - Optional CSS class name override for custom styling.
 */
export function TimelineCard({ time, title, desc, icon: Icon, colorClass = 'bg-white', isLast = false, className = '' }) {
  const containerClasses = `flex gap-4 select-none ${className}`.trim();

  return (
    <div className={containerClasses}>
      <div className="flex flex-col items-center flex-shrink-0">
        <div className={`w-8 h-8 rounded-none border border-[var(--border-default)] flex items-center justify-center shadow-sm relative z-10 ${colorClass}`}>
          {Icon ? <Icon size={14} className="text-[var(--text-primary)]" /> : '📍'}
        </div>
        {!isLast && <div className="w-[1.5px] bg-[var(--border-default)] flex-1 my-1" />}
      </div>
      
      <div className="flex-1 pb-6">
        <div className="font-mono text-[9px] uppercase font-bold text-[var(--text-muted)] mb-1">{time}</div>
        <div className="border border-[var(--border-default)] bg-[var(--bg-primary)] p-3.5 rounded-none shadow-sm hover:border-[var(--accent-indigo)] transition-all">
          <h4 className="font-sans font-extrabold text-xs text-[var(--text-primary)] uppercase leading-tight">{title}</h4>
          {desc && <p className="font-mono text-[10px] text-[var(--text-secondary)] mt-1.5 leading-relaxed">{desc}</p>}
        </div>
      </div>
    </div>
  );
}
