import React, { useState, useRef } from 'react';
import { motion } from 'framer-motion';

/**
 * DonutChart — Animated SVG donut chart for displaying a single percentage metric.
 *
 * Props:
 *   percent   {number}  - Value 0–100 to fill.
 *   label     {string}  - Center label text (e.g. "Score").
 *   value     {string}  - Center value text (e.g. "82%").
 *   color     {string}  - Fill color (CSS variable or hex).
 *   size      {number}  - SVG width/height in px (default: 120).
 *   thickness {number}  - Stroke width (default: 14).
 */
export function DonutChart({
  percent = 0,
  label = '',
  value = '',
  color = 'var(--yellow)',
  size = 120,
  thickness = 14,
}) {
  const [hovered, setHovered] = useState(false);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const cx = size / 2;
  const cy = size / 2;
  const clampedPercent = Math.min(100, Math.max(0, percent));
  const strokeDashoffset = circumference * (1 - clampedPercent / 100);

  return (
    <div
      className="relative inline-flex items-center justify-center select-none"
      style={{ width: size, height: size }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={`${label}: ${clampedPercent}%`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Track ring */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke="var(--black)"
          strokeWidth={thickness}
          opacity={0.08}
        />

        {/* Progress arc */}
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
          animate={{ strokeDashoffset }}
          transition={{ duration: 1.0, ease: 'easeOut' }}
          style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
        />
      </svg>

      {/* Center text */}
      <div className="absolute inset-0 flex flex-col items-center justify-center font-mono">
        <motion.span
          className="text-base font-black leading-none"
          animate={{ scale: hovered ? 1.1 : 1 }}
          transition={{ duration: 0.2 }}
          style={{ color: 'var(--black)' }}
        >
          {value || `${clampedPercent}%`}
        </motion.span>
        {label && (
          <span
            className="text-[9px] font-bold uppercase tracking-tight opacity-60 mt-0.5"
            style={{ color: 'var(--black)' }}
          >
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
