import React from 'react';
import { motion } from 'framer-motion';

export function LoadingSkeleton({ rows = 4, className = '' }) {
  return (
    <div className={`flex flex-col gap-4 w-full p-4 select-none ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 items-center">
          <motion.div
            className="w-10 h-10 bg-neutral-100 rounded-full border border-neutral-200/50 flex-shrink-0"
            animate={{ opacity: [0.4, 0.8, 0.4] }}
            transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.15 }}
          />
          <div className="flex-1 flex flex-col gap-2">
            <motion.div
              className="h-4 bg-neutral-100 rounded-lg border border-neutral-200/50 w-[60%]"
              animate={{ opacity: [0.4, 0.8, 0.4] }}
              transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.15 + 0.15 }}
            />
            <motion.div
              className="h-3 bg-neutral-100 rounded-lg border border-neutral-200/50 w-[90%]"
              animate={{ opacity: [0.4, 0.8, 0.4] }}
              transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.15 + 0.3 }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
