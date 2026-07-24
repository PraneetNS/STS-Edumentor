import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

/**
 * StatCard component to display a key metric or count with counter counting animation.
 *
 * @param {Object} props
 * @param {string} props.label - The uppercase header label for the stat card.
 * @param {number|string} props.value - The value to display (counts are animated if type is number).
 * @param {string} [props.desc] - Optional detail summary sentence.
 * @param {React.ComponentType<{ size: number, className: string }>} [props.icon] - Optional React Lucide/SVG icon component.
 * @param {string} [props.colorClass='bg-white'] - Optional extra tailwind background classes.
 * @param {boolean} [props.animate=true] - If true and value is a number, animates the display counting up.
 * @param {string} [props.className=''] - Optional CSS class name override for custom styling.
 */
export function StatCard({ label, value, desc, icon: Icon, colorClass = 'bg-white', animate = true, className = '' }) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    if (!animate || typeof value !== 'number') {
      setDisplayValue(value);
      return;
    }
    
    let start = 0;
    const end = value;
    if (start === end) return;
    
    const duration = 1200; // ms
    const increment = end > 100 ? Math.ceil(end / 30) : 1;
    const stepTime = Math.max(Math.floor(duration / (end / increment)), 15);
    
    const timer = setInterval(() => {
      start += increment;
      if (start >= end) {
        setDisplayValue(end);
        clearInterval(timer);
      } else {
        setDisplayValue(start);
      }
    }, stepTime);
    
    return () => clearInterval(timer);
  }, [value, animate]);

  const containerClasses = `border border-[var(--border-default)]/60 p-6 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.03)] text-[var(--text-primary)] flex flex-col justify-between relative overflow-hidden cursor-default bg-[var(--bg-primary)]/80 backdrop-blur-md ${colorClass} ${className}`.trim();

  return (
    <motion.div
      className={containerClasses}
      whileHover={{ y: -3, scale: 1.01, boxShadow: '0 12px 40px rgb(0 0 0 / 0.05)' }}
      transition={{ type: 'spring', stiffness: 350, damping: 15 }}
      style={{ minWidth: 0 }}
    >
      <div className="flex justify-between items-start gap-4">
        <span className="font-sans text-[10.5px] uppercase font-bold text-[var(--text-muted)] tracking-wider truncate">{label}</span>
        {Icon && <Icon size={16} className="text-indigo-400 flex-shrink-0" />}
      </div>
      
      <div className="mt-4">
        <h3 className="font-sans font-extrabold text-3xl leading-tight truncate text-[var(--text-primary)]">
          {typeof value === 'number' ? displayValue.toLocaleString() : value}
        </h3>
        {desc && <p className="font-sans text-[11px] font-medium text-[var(--text-muted)] mt-1.5 leading-snug break-words">{desc}</p>}
      </div>
    </motion.div>
  );
}
