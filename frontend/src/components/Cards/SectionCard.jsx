import React from 'react';
import { motion } from 'framer-motion';

export function SectionCard({ title, subtitle, headerAction, headerBg = 'bg-[var(--bg-tertiary)]', children, className = '' }) {
  return (
    <div className={`border border-[var(--border-default)] bg-[var(--bg-primary)] rounded-none shadow-sm overflow-hidden flex flex-col ${className}`}>
      {(title || subtitle || headerAction) && (
        <div className={`px-5 py-4 border-b border-[var(--border-default)] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 ${headerBg}`}>
          <div>
            {title && <h3 className="font-sans font-extrabold text-sm uppercase text-[var(--text-primary)] tracking-wide leading-tight">{title}</h3>}
            {subtitle && <p className="font-mono text-[9.5px] text-[var(--text-muted)] mt-0.5 tracking-tight leading-tight">{subtitle}</p>}
          </div>
          {headerAction && <div className="flex-shrink-0">{headerAction}</div>}
        </div>
      )}
      <div className="p-5 flex-1 flex flex-col bg-[var(--bg-primary)] text-[var(--text-primary)]">
        {children}
      </div>
    </div>
  );
}
