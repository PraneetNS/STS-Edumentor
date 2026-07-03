import React from 'react';
import { Tooltip } from './Tooltip';

export function Badge({ name, icon = '🏆', desc, unlocked = false }) {
  return (
    <Tooltip text={`${name}: ${desc}`}>
      <div 
        className={`flex flex-col items-center justify-center p-4 border rounded-none text-center transition-all ${
          unlocked 
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-400 hover:bg-amber-500/20 cursor-pointer shadow-sm' 
            : 'bg-[var(--bg-tertiary)] border-[var(--border-default)] opacity-40 cursor-not-allowed select-none text-[var(--text-muted)]'
        }`}
      >
        <div className="text-2xl mb-2">{unlocked ? icon : '🔒'}</div>
        <div className="font-sans font-bold text-[10.5px] text-[var(--text-primary)] leading-tight truncate w-full">{name}</div>
        <div className="font-sans text-[8px] text-[var(--text-muted)] mt-1 uppercase font-bold tracking-tight">
          {unlocked ? 'Unlocked' : 'Locked'}
        </div>
      </div>
    </Tooltip>
  );
}
