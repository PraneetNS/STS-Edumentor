import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export function StatCard({ label, value, desc, icon: Icon, colorClass = 'bg-white', animate = true }) {
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

  return (
    <motion.div
      className={`border border-[var(--border-default)] p-5 rounded-none shadow-sm text-[var(--text-primary)] flex flex-col justify-between relative overflow-hidden cursor-default bg-[var(--bg-primary)] ${colorClass}`}
      whileHover={{ y: -1, boxShadow: 'var(--shadow-md)' }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      style={{ minWidth: 0 }}
    >
      <div className="flex justify-between items-start gap-4">
        <span className="font-mono text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider truncate">{label}</span>
        {Icon && <Icon size={16} className="text-[var(--text-secondary)] flex-shrink-0" />}
      </div>
      
      <div className="mt-4">
        <h3 className="font-sans font-extrabold text-3xl leading-tight truncate text-[var(--text-primary)]">
          {typeof value === 'number' ? displayValue.toLocaleString() : value}
        </h3>
        {desc && <p className="font-mono text-[10px] text-[var(--text-muted)] mt-1 leading-snug break-words">{desc}</p>}
      </div>
    </motion.div>
  );
}
