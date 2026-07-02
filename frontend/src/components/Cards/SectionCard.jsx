import React from 'react';
import { motion } from 'framer-motion';

export function SectionCard({ title, subtitle, headerAction, headerBg = 'bg-neutral-50/50', children, className = '' }) {
  return (
    <div className={`border border-neutral-200 bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col ${className}`}>
      {(title || subtitle || headerAction) && (
        <div className={`px-5 py-4 border-b border-neutral-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 ${headerBg}`}>
          <div>
            {title && <h3 className="font-sans font-extrabold text-sm uppercase text-black tracking-wide leading-tight">{title}</h3>}
            {subtitle && <p className="font-mono text-[9.5px] text-black/75 mt-0.5 tracking-tight leading-tight">{subtitle}</p>}
          </div>
          {headerAction && <div className="flex-shrink-0">{headerAction}</div>}
        </div>
      )}
      <div className="p-5 flex-1 flex flex-col bg-white">
        {children}
      </div>
    </div>
  );
}
