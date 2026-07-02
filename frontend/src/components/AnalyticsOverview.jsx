import React from 'react';
import { SectionCard } from './Cards/SectionCard';
import { StatCard } from './Cards/StatCard';
import { LineChart } from './Charts/LineChart';
import { ProgressRing } from './Charts/ProgressRing';
import { Heatmap } from './Charts/Heatmap';
import { SkillBar } from './Charts/SkillBar';
import { ChevronLeft, BarChart2, Activity, Calendar, Trophy, MessageSquare, Clock } from 'lucide-react';
import { FloatingShapes } from './FloatingShapes';
import mockAnalytics from '../data/analytics.json';

export function AnalyticsOverview({ onBack }) {
  const { readiness, stats, weaknesses, heatmap, weekly_trend, question_difficulty, topic_distribution } = mockAnalytics;

  // Compute stacked difficulty ratio calculations
  const totalSolved = question_difficulty.easy + question_difficulty.medium + question_difficulty.hard || 1;
  const pctEasy = (question_difficulty.easy / totalSolved) * 100;
  const pctMedium = (question_difficulty.medium / totalSolved) * 100;
  const pctHard = (question_difficulty.hard / totalSolved) * 100;

  return (
    <div className="relative min-h-screen w-full px-4 md:px-8 py-6 bg-white select-none">
      {/* Background shape animation */}
      <FloatingShapes page="profile" />

      <div className="w-full relative z-10">
        
        {/* HEADER CONTROLS */}
        <div className="flex items-center justify-between mb-8">
          <button 
            onClick={onBack} 
            className="flex items-center gap-2 font-sans font-semibold text-xs text-neutral-600 bg-white border border-neutral-200 px-4 py-2.5 rounded-full hover:bg-neutral-50 transition-all cursor-pointer shadow-sm"
          >
            <ChevronLeft size={16} /> Back to Mentor
          </button>
        </div>

        {/* SECTION TITLE */}
        <div className="mb-8">
          <span className="section-tag">Insights Station</span>
          <h2 className="section-title">GitHub Insights & Performance</h2>
        </div>

        {/* 12-COLUMN DASHBOARD GRID */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          
          {/* LEFT 4 COLS: GENERAL READINESS PROFILE SUMMARY */}
          <div className="md:col-span-12 lg:col-span-4 flex flex-col gap-6">
            
            <SectionCard title="Overall Readiness" subtitle="Weighted placement probability indexes" headerBg="bg-neutral-50/50">
              <div className="flex flex-col items-center gap-6 py-4">
                <div className="flex justify-around w-full">
                  <ProgressRing score={readiness.placement_score} size={90} color="var(--accent-teal)" label="Placement" />
                  <ProgressRing score={readiness.interview_score} size={90} color="var(--accent-coral)" label="Interview" />
                </div>
                
                <div className="w-full border-t border-neutral-150 pt-4 font-sans text-xs text-neutral-500 leading-relaxed flex flex-col gap-2">
                  <div className="flex justify-between">
                    <span>Revision consistency:</span>
                    <strong className="text-neutral-800 font-semibold">{readiness.revision_score}%</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Coding confidence:</span>
                    <strong className="text-neutral-800 font-semibold">{readiness.coding_confidence}%</strong>
                  </div>
                </div>
              </div>
            </SectionCard>

            {/* Quick Insights Cards */}
            <div className="grid grid-cols-2 gap-4">
              <StatCard label="Total Queries" value={stats.questions_asked} desc="Questions submitted to EDI" icon={MessageSquare} colorClass="bg-white" />
              <StatCard label="Session Hours" value={Math.round(stats.study_hours)} desc="Voice duration hours" icon={Clock} colorClass="bg-white" />
            </div>

            <SectionCard title="Priority Focus Areas" subtitle="Analysis of study weaknesses" headerBg="bg-neutral-50/50">
              <div className="font-sans text-xs flex flex-col gap-3">
                <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex flex-col">
                  <span className="text-[9px] font-semibold text-neutral-450 uppercase">Weakest Concept</span>
                  <span className="font-sans font-bold text-sm text-red-500 mt-1">{weaknesses.weakest_topic}</span>
                </div>
                <div className="border border-neutral-200 p-3.5 rounded-xl bg-neutral-50/50 flex flex-col">
                  <span className="text-[9px] font-semibold text-neutral-450 uppercase">Most Practiced Track</span>
                  <span className="font-sans font-bold text-sm text-neutral-800 mt-1">{weaknesses.most_practiced_subject}</span>
                </div>
              </div>
            </SectionCard>

          </div>

          {/* RIGHT 8 COLS: GITHUB HEATMAP, VELOCITY CURVES, PROGRESS LIST */}
          <div className="md:col-span-12 lg:col-span-8 flex flex-col gap-6">
            
            {/* GitHub Insights Heatmap */}
            <SectionCard title="Consistency Calendar" subtitle="Commitment frequency of voice tutoring sessions" headerBg="bg-neutral-50/50">
              <div className="py-2">
                <Heatmap data={heatmap} />
              </div>
            </SectionCard>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              
              {/* Stacked difficulty rating */}
              <SectionCard title="Question Difficulty" subtitle="Solved problems split ratio" headerBg="bg-neutral-50/50">
                <div className="flex flex-col justify-between h-full font-sans text-xs">
                  <div className="flex flex-col gap-2 py-4">
                    <div className="h-4 border border-neutral-200 rounded-full overflow-hidden flex shadow-sm">
                      <div className="h-full bg-[var(--accent-teal)] border-r border-white/20" style={{ width: `${pctEasy}%` }} title="Easy" />
                      <div className="h-full bg-[var(--accent-amber)] border-r border-white/20" style={{ width: `${pctMedium}%` }} title="Medium" />
                      <div className="h-full bg-[var(--accent-coral)]" style={{ width: `${pctHard}%` }} title="Hard" />
                    </div>

                    <div className="flex justify-between items-center text-[10.5px] mt-1.5 font-medium text-neutral-600">
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-teal)]" /> Easy ({question_difficulty.easy})</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-amber)]" /> Medium ({question_difficulty.medium})</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-coral)]" /> Hard ({question_difficulty.hard})</span>
                    </div>
                  </div>
                  
                  <div className="border-t border-neutral-100 pt-2.5 text-center text-[10px] font-semibold text-neutral-450">
                    Total Solved Problems: {totalSolved}
                  </div>
                </div>
              </SectionCard>

              {/* LineChart learning curve */}
              <SectionCard title="Learning Velocity" subtitle="Interaction turn velocity trend" headerBg="bg-neutral-50/50">
                <div className="py-2">
                  <LineChart data={[
                    { label: 'W1', value: 4 },
                    { label: 'W2', value: 8 },
                    { label: 'W3', value: 14 },
                    { label: 'W4', value: 19 },
                    { label: 'W5', value: 27 },
                    { label: 'W6', value: 37 }
                  ]} height={100} color="var(--blue-200)" />
                </div>
              </SectionCard>

            </div>

            {/* Horizontal rankings list card */}
            <SectionCard title="Subject Area Mastery Ratings" subtitle="Competency percentages by core discipline module" headerBg="bg-neutral-50/50">
              <div className="flex flex-col gap-4 py-2">
                {topic_distribution.map((topic, idx) => {
                  const colors = ['var(--accent-amber)', 'var(--accent-coral)', 'var(--accent-teal)', 'var(--blue-400)'];
                  const colorIdx = idx % colors.length;
                  return (
                    <SkillBar
                      key={idx}
                      label={topic.subject}
                      percent={topic.percentage}
                      color={colors[colorIdx]}
                    />
                  );
                })}
              </div>
            </SectionCard>

          </div>

        </div>

      </div>
    </div>
  );
}
export default AnalyticsOverview;
