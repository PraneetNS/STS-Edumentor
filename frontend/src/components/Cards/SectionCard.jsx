import React from 'react';
import { motion } from 'framer-motion';

export function SectionCard({ title, subtitle, headerAction, headerBg = 'bg-[var(--bg-tertiary)]/30', children, className = '' }) {
  return (
    <div className={`border border-[var(--border-default)]/60 bg-[var(--bg-primary)]/80 backdrop-blur-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.03)] overflow-hidden flex flex-col transition-all duration-300 hover:shadow-[0_12px_40px_rgb(0,0,0,0.05)] ${className}`}>
      {(title || subtitle || headerAction) && (
        <div className={`px-6 py-4.5 border-b border-[var(--border-default)]/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 ${headerBg}`}>
          <div>
            {title && (
              <h3 className="font-sans font-bold text-sm text-[var(--text-primary)] tracking-wide leading-tight">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="font-sans text-[10px] text-[var(--text-muted)] mt-1 tracking-normal leading-tight font-medium">
                {subtitle}
              </p>
            )}
          </div>
          {headerAction && <div className="flex-shrink-0">{headerAction}</div>}
        </div>
      )}
      <div className="p-6 flex-1 flex flex-col text-[var(--text-primary)]">
        {children}
      </div>
    </div>
  );
}
