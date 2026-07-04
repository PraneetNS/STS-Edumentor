import React from 'react';
import { motion } from 'framer-motion';

export function EmptyState({ onBack, className = "" }) {
  const containerClasses = `flex flex-col items-center justify-center p-8 text-center bg-neutral-50/50 border border-neutral-200 rounded-2xl shadow-sm my-6 select-none max-w-lg mx-auto ${className}`.trim();

  return (
    <div className={containerClasses}>
      <motion.div
        className="text-4xl mb-4"
        animate={{ y: [0, -8, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      >
        📚
      </motion.div>
      <h3 className="font-sans font-bold text-base text-neutral-800 mb-2">
        Start your first conversation
      </h3>
      <p className="font-sans text-xs text-neutral-500 max-w-sm mx-auto mb-5 leading-relaxed">
        Your learning journey begins here. Talk to EDI to generate placement readiness profiles, study hours, and activity heatmaps.
      </p>
      {onBack && (
        <button 
          onClick={onBack}
          className="bg-blue-500 hover:bg-blue-600 text-white font-sans font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-all cursor-pointer text-[11px]"
        >
          Launch Voice Session
        </button>
      )}
    </div>
  );
}
