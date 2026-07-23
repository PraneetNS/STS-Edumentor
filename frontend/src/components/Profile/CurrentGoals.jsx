import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { CheckSquare, Square, Play, Clock, Sparkles } from 'lucide-react';

export function CurrentGoals({ today = {}, onContinue, onGoalToggle }) {
  const { greeting, goals = [], estimated_time_mins } = today;
  const [localGoals, setLocalGoals] = useState(goals);

  // Re-sync if goals prop changes (e.g. after stats load)
  React.useEffect(() => {
    setLocalGoals(goals);
  }, [JSON.stringify(goals)]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleGoal = (id) => {
    setLocalGoals(prev => {
      const updated = prev.map(g => g.id === id ? { ...g, completed: !g.completed } : g);
      const toggled = updated.find(g => g.id === id);
      // Persist to localStorage via callback
      onGoalToggle?.(id, toggled?.completed ?? false);
      return updated;
    });
  };

  const hours = Math.floor(estimated_time_mins / 60);
  const mins = estimated_time_mins % 60;
  const timeString = `${hours > 0 ? `${hours} hr ` : ''}${mins} mins`;

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] p-6 rounded-none shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-6 select-none relative overflow-hidden text-[var(--text-primary)]">
      
      {/* Background visual detail */}
      <div className="absolute right-[-10px] top-[-10px] opacity-5 pointer-events-none text-[var(--text-tertiary)]">
        <Sparkles size={140} />
      </div>

      <div className="flex-1">
        <h3 className="font-sans font-bold text-lg text-[var(--text-primary)] leading-tight">
          {greeting || 'Welcome Candidate 👋'}
        </h3>
        
        {/* Goals Checklist */}
        <div className="mt-3 flex flex-col gap-2.5 font-sans text-xs text-[var(--text-secondary)]">
          {localGoals.map(goal => (
            <div
              key={goal.id}
              onClick={() => toggleGoal(goal.id)}
              className="flex items-center gap-2 cursor-pointer group w-fit hover:opacity-85"
            >
              {goal.completed ? (
                <CheckSquare size={14} className="text-[var(--accent-mint)] flex-shrink-0" />
              ) : (
                <Square size={14} className="text-[var(--text-tertiary)] flex-shrink-0" />
              )}
              <span className={`leading-normal ${goal.completed ? 'line-through opacity-55 text-[var(--text-muted)]' : 'font-semibold text-[var(--text-primary)]'}`}>
                {goal.label}
              </span>
            </div>
          ))}
          {localGoals.length === 0 && (
            <p className="text-[var(--text-muted)] opacity-60">Start a session to unlock your daily goals.</p>
          )}
        </div>
      </div>

      {/* Action panel */}
      <div className="flex-shrink-0 flex flex-col gap-3 w-full md:w-auto relative z-10">
        <div className="flex items-center gap-2 font-sans text-[11px] font-semibold text-[var(--text-muted)] md:justify-end">
          <Clock size={12} />
          <span>Estimated study: {timeString}</span>
        </div>
        
        <button
          onClick={onContinue}
          className="bg-[var(--accent-indigo)] hover:bg-[var(--accent-indigo-light)] text-white font-sans font-semibold px-6 py-3 rounded-none transition-all cursor-pointer flex items-center justify-center gap-2 text-xs shadow-sm"
        >
          <Play size={10} fill="currentColor" /> Continue Learning
        </button>
      </div>

    </div>
  );
}
