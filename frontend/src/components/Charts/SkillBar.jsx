import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export function SkillBar({ label, percent = 0, color = 'var(--yellow)' }) {
  const [animatedPercent, setAnimatedPercent] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setAnimatedPercent(percent), 150);
    return () => clearTimeout(timer);
  }, [percent]);

  return (
    <div className="flex flex-col gap-1 w-full font-mono select-none">
      <div className="flex justify-between items-center text-[10px] font-bold text-black uppercase tracking-tight">
        <span className="truncate max-w-[80%]">{label}</span>
        <span>{percent}%</span>
      </div>
      
      <div className="h-4 bg-white border-2 border-black rounded-lg overflow-hidden relative shadow-sm">
        <motion.div
          className="h-full border-r-2 border-black"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${animatedPercent}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}
