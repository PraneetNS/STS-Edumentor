import React from 'react';

export function Pill({ text, color = 'var(--yellow)', textColor = 'var(--black)' }) {
  return (
    <span 
      className="inline-flex items-center font-sans font-semibold text-[9.5px] px-2.5 py-0.5 border border-black/5 rounded-full"
      style={{ backgroundColor: color, color: textColor }}
    >
      {text}
    </span>
  );
}
