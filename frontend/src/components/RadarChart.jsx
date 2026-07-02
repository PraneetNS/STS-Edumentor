import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const AXES = [
  { key: 'cse', name: 'Comp Sci (CSE)' },
  { key: 'mech', name: 'Mechanical (ME)' },
  { key: 'eee', name: 'Electrical (EE)' },
  { key: 'civil', name: 'Civil (CE)' },
  { key: 'chemical', name: 'Chemical (ChE)' },
  { key: 'aerospace', name: 'Aerospace (AE)' }
];

export function RadarChart({ data }) {
  const [animatedScale, setAnimatedScale] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setAnimatedScale(1), 100);
    return () => clearTimeout(timer);
  }, []);

  const cx = 200;
  const cy = 200;
  const R = 115;

  const getCoordinates = (index, value) => {
    const angle = (index * 2 * Math.PI) / 6 - Math.PI / 2;
    const x = cx + R * value * Math.cos(angle);
    const y = cy + R * value * Math.sin(angle);
    return { x, y, angle };
  };

  const levels = [0.2, 0.4, 0.6, 0.8, 1.0];

  const points = AXES.map((axis, i) => {
    const depth = data?.[axis.key] ?? 0.0;
    const coords = getCoordinates(i, depth * animatedScale);
    return `${coords.x},${coords.y}`;
  }).join(' ');

  return (
    <div className="flex flex-col items-center justify-center p-4 w-full" style={{ fontFamily: 'var(--font-mono)' }}>
      <svg viewBox="0 0 400 400" className="w-full max-w-[340px] select-none overflow-visible">
        {/* Background Grid Lines (Concentric Polygons) */}
        {levels.map((level, idx) => {
          const levelPoints = AXES.map((_, i) => {
            const coords = getCoordinates(i, level);
            return `${coords.x},${coords.y}`;
          }).join(' ');
          
          return (
            <polygon
              key={idx}
              points={levelPoints}
              fill="none"
              stroke="var(--black)"
              strokeWidth="2"
              strokeDasharray="4 4"
              opacity="0.3"
            />
          );
        })}

        {/* Axis spoke lines */}
        {AXES.map((axis, i) => {
          const outerCoords = getCoordinates(i, 1.0);
          const labelCoords = getCoordinates(i, 1.25);
          const val = data?.[axis.key] ?? 0.0;
          
          let textAnchor = 'middle';
          if (labelCoords.x < cx - 20) textAnchor = 'end';
          if (labelCoords.x > cx + 20) textAnchor = 'start';

          return (
            <g key={axis.key}>
              <line
                x1={cx}
                y1={cy}
                x2={outerCoords.x}
                y2={outerCoords.y}
                stroke="var(--black)"
                strokeWidth="2"
                opacity="0.25"
              />
              
              {/* Category label */}
              <text
                x={labelCoords.x}
                y={labelCoords.y}
                fill="var(--black)"
                fontSize="10"
                fontWeight="700"
                fontFamily="var(--font-sans)"
                textAnchor={textAnchor}
              >
                {axis.name.toUpperCase()}
              </text>
              
              {/* Score label */}
              <text
                x={labelCoords.x}
                y={labelCoords.y + 13}
                fill="var(--coral)"
                fontSize="10.5"
                fontWeight="800"
                fontFamily="var(--font-mono)"
                textAnchor={textAnchor}
              >
                {Math.round(val * 100)}%
              </text>
            </g>
          );
        })}

        {/* Radar Value Fill Polygon */}
        {points && (
          <motion.polygon
            points={points}
            fill="var(--lavender)"
            fillOpacity="0.7"
            stroke="var(--black)"
            strokeWidth="3.5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        )}

        {/* Node point circular markers */}
        {AXES.map((axis, i) => {
          const depth = data?.[axis.key] ?? 0.0;
          const coords = getCoordinates(i, depth * animatedScale);
          return (
            <circle
              key={axis.key}
              cx={coords.x}
              cy={coords.y}
              r="6.5"
              fill="var(--yellow)"
              stroke="var(--black)"
              strokeWidth="2.5"
            />
          );
        })}
      </svg>
    </div>
  );
}
