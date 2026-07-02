import React from 'react';
import { ProgressRing } from '../Charts/ProgressRing';
import { Zap, Clock, Activity, BarChart2 } from 'lucide-react';

export function LearningSnapshot({ score = 75, stats = {}, weaknesses = {} }) {
  const { study_hours, average_response_delay_sec, weekly_improvement_percentage } = stats;
  const { most_practiced_subject } = weaknesses;

  return (
    <div className="w-full flex flex-col md:flex-row gap-6 items-center select-none bg-transparent">
      {/* Progress ring area */}
      <div className="flex-shrink-0 flex items-center justify-center">
        <ProgressRing score={score} size={110} color="var(--accent-coral)" label="Readiness" />
      </div>

      {/* Snapshot metrics */}
      <div className="flex-1 w-full grid grid-cols-2 gap-4">
        
        <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex items-center gap-3">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0">
            <Clock size={14} />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-sans text-[9.5px] text-neutral-450 uppercase font-semibold tracking-wider truncate">Study Hours</span>
            <span className="font-sans font-bold text-sm text-neutral-800 truncate">{study_hours || 0} Hours</span>
          </div>
        </div>

        <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex items-center gap-3">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0">
            <Activity size={14} />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-sans text-[9.5px] text-neutral-450 uppercase font-semibold tracking-wider truncate">Consistency</span>
            <span className="font-sans font-bold text-sm text-neutral-800 truncate">92.4% Score</span>
          </div>
        </div>

        <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex items-center gap-3">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0">
            <Zap size={14} />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-sans text-[9.5px] text-neutral-450 uppercase font-semibold tracking-wider truncate">Avg Latency</span>
            <span className="font-sans font-bold text-sm text-neutral-800 truncate">{average_response_delay_sec || 0}s Delay</span>
          </div>
        </div>

        <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex items-center gap-3">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0">
            <BarChart2 size={14} />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-sans text-[9.5px] text-neutral-450 uppercase font-semibold tracking-wider truncate">Active Focus</span>
            <span className="font-sans font-bold text-xs text-neutral-800 truncate leading-tight">{most_practiced_subject || 'DSA'}</span>
          </div>
        </div>

      </div>
    </div>
  );
}
