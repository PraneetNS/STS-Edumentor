import React from 'react';
import { motion } from 'framer-motion';

export function LineChart({ data = [], height = 120, color = 'var(--yellow)', fillOpacity = 0.15 }) {
  const width = 360;
  const padding = 20;

  const values = data.map(d => d.value || 0);
  const maxVal = Math.max(...values, 10);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1 || 1)) * (width - padding * 2);
    const y = height - padding - ((d.value - minVal) / range) * (height - padding * 2);
    return { x, y, label: d.label, value: d.value };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const areaPath = points.length > 0 
    ? `${linePath} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`
    : '';

  return (
    <div className="w-full flex flex-col gap-2 font-mono select-none">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full overflow-visible">
        {/* Draw background grid lines */}
        {Array.from({ length: 4 }).map((_, idx) => {
          const y = padding + (idx / 3) * (height - padding * 2);
          return (
            <line
              key={idx}
              x1={padding}
              y1={y}
              x2={width - padding}
              y2={y}
              stroke="var(--black)"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              opacity="0.1"
            />
          );
        })}

        {/* Draw Line Area and Stroke with Animations */}
        {points.length > 0 && (
          <>
            <motion.path
              d={areaPath}
              fill={color}
              opacity={fillOpacity}
              initial={{ opacity: 0 }}
              animate={{ opacity: fillOpacity }}
              transition={{ duration: 0.5 }}
            />
            
            <motion.path
              d={linePath}
              fill="none"
              stroke="var(--black)"
              strokeWidth="2.5"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
            
            {/* Draw Dot Ticks and values */}
            {points.map((p, idx) => (
              <g key={idx}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="3.5"
                  fill="var(--white)"
                  stroke="var(--black)"
                  strokeWidth="2"
                />
                
                {/* Tick label at the bottom */}
                <text
                  x={p.x}
                  y={height - 4}
                  fontSize="7"
                  fontWeight="bold"
                  textAnchor="middle"
                  fill="var(--black)"
                  opacity="0.6"
                >
                  {p.label}
                </text>

                {/* Score value above dot */}
                <text
                  x={p.x}
                  y={p.y - 8}
                  fontSize="7"
                  fontWeight="800"
                  textAnchor="middle"
                  fill="var(--black)"
                  opacity="0.8"
                >
                  {p.value}
                </text>
              </g>
            ))}
          </>
        )}
      </svg>
    </div>
  );
}
