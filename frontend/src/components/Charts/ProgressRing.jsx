import React from 'react';
import { motion } from 'framer-motion';

export function ProgressRing({ score = 0, size = 110, strokeWidth = 8, color = 'var(--coral)', label = 'Score' }) {
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center select-none" style={{ width: size, height: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle 
            cx={size / 2} 
            cy={size / 2} 
            r={radius} 
            fill="none" 
            stroke="rgba(13, 13, 13, 0.08)" 
            strokeWidth={strokeWidth} 
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={circumference}
            animate={{ strokeDashoffset }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center font-mono">
          <span className="font-sans font-extrabold text-xl text-black leading-none">{score}%</span>
          {label && <span className="text-[7px] text-black/60 uppercase font-bold mt-1 tracking-wider">{label}</span>}
        </div>
      </div>
    </div>
  );
}
