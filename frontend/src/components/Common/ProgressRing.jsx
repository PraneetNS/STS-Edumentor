import React from 'react';
import { motion } from 'framer-motion';

/**
 * ProgressRing — Animated SVG circular progress indicator.
 *
 * Lighter alternative to DonutChart: no hover state, no center label variants,
 * designed for compact inline usage (e.g. inside stat cards, list rows).
 *
 * Props:
 *   percent   {number}  0-100
 *   size      {number}  SVG width/height in px (default: 48)
 *   thickness {number}  Stroke width (default: 5)
 *   color     {string}  Progress arc color
 *   trackColor{string}  Background track color
 *   children  {ReactNode} Optional center content
 */
export function ProgressRing({
  percent = 0,
  size = 48,
  thickness = 5,
  color = 'var(--yellow)',
  trackColor = 'rgba(0,0,0,0.08)',
  children,
}) {
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, percent));
  const offset = circumference * (1 - clamped / 100);
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div
      className="relative inline-flex items-center justify-center flex-shrink-0"
      style={{ width: size, height: size }}
      aria-label={`${clamped}% progress`}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Track */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={thickness}
        />
        {/* Arc */}
        <motion.circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
          style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
        />
      </svg>

      {children && (
        <div className="absolute inset-0 flex items-center justify-center">
          {children}
        </div>
      )}
    </div>
  );
}
