import React from 'react';
import { Tooltip } from './Tooltip';

export function Badge({ name, icon = '🏆', desc, unlocked = false }) {
  return (
    <Tooltip text={`${name}: ${desc}`}>
      <div 
        className={`flex flex-col items-center justify-center p-4 border rounded-2xl text-center transition-all ${
          unlocked 
            ? 'bg-amber-50/30 border-amber-200 text-amber-900 hover:bg-amber-50/70 hover:shadow-sm cursor-pointer' 
            : 'bg-neutral-50 border-neutral-200 opacity-50 cursor-not-allowed select-none'
        }`}
      >
        <div className="text-2xl mb-2">{unlocked ? icon : '🔒'}</div>
        <div className="font-sans font-bold text-[10.5px] text-neutral-800 leading-tight truncate w-full">{name}</div>
        <div className="font-sans text-[8px] text-neutral-400 mt-1 uppercase font-bold tracking-tight">
          {unlocked ? 'Unlocked' : 'Locked'}
        </div>
      </div>
    </Tooltip>
  );
}
