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
      className={`border border-neutral-200 p-5 rounded-2xl shadow-sm text-black flex flex-col justify-between relative overflow-hidden cursor-default ${colorClass}`}
      whileHover={{ y: -1, boxShadow: 'var(--shadow-flat-md)' }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      style={{ minWidth: 0 }}
    >
      <div className="flex justify-between items-start gap-4">
        <span className="font-mono text-[9px] uppercase font-bold text-black/60 tracking-wider truncate">{label}</span>
        {Icon && <Icon size={16} className="text-black/70 flex-shrink-0" />}
      </div>
      
      <div className="mt-4">
        <h3 className="font-sans font-extrabold text-3xl leading-tight truncate text-black">
          {typeof value === 'number' ? displayValue.toLocaleString() : value}
        </h3>
        {desc && <p className="font-mono text-[10px] text-black/60 mt-1 leading-snug break-words">{desc}</p>}
      </div>
    </motion.div>
  );
}
