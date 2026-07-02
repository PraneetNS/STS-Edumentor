import React from 'react';
import { motion } from 'framer-motion';

export function TimelineCard({ time, title, desc, icon: Icon, colorClass = 'bg-white', isLast = false }) {
  return (
    <div className="flex gap-4 select-none">
      <div className="flex flex-col items-center flex-shrink-0">
        <div className={`w-8 h-8 rounded-full border border-neutral-200 flex items-center justify-center shadow-sm relative z-10 ${colorClass}`}>
          {Icon ? <Icon size={14} className="text-neutral-700" /> : '📍'}
        </div>
        {!isLast && <div className="w-[1.5px] bg-neutral-200 flex-1 my-1" />}
      </div>
      
      <div className="flex-1 pb-6">
        <div className="font-mono text-[9px] uppercase font-bold text-black/40 mb-1">{time}</div>
        <div className="border border-neutral-200 bg-white p-3.5 rounded-xl shadow-sm hover:shadow-md hover:border-blue-200 transition-all">
          <h4 className="font-sans font-extrabold text-xs text-black uppercase leading-tight">{title}</h4>
          {desc && <p className="font-mono text-[10px] text-black/60 mt-1.5 leading-relaxed">{desc}</p>}
        </div>
      </div>
    </div>
  );
}
