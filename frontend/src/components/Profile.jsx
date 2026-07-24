import React, { useEffect, useState } from 'react';
import { HeroCard } from './Profile/HeroCard';
import { LearningSnapshot } from './Profile/LearningSnapshot';
import { CurrentGoals } from './Profile/CurrentGoals';
import { AchievementGrid } from './Profile/AchievementGrid';
import { ActivityTimeline } from './Profile/ActivityTimeline';
import { SectionCard } from './Cards/SectionCard';
import { SkillBar } from './Charts/SkillBar';
import { RadarChart } from './RadarChart';
import { ChevronLeft, RefreshCw } from 'lucide-react';
import { useProfileStats, persistGoalToggle } from '../hooks/useProfileStats';
import { authStore } from '../stores/authStore';

export function Profile({ onBack, conversations = [], setView }) {
  const [animateProgress, setAnimateProgress] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setAnimateProgress(true), 150);
    return () => clearTimeout(timer);
  }, []);

  const {
    loading,
    error,
    refresh,
    lastFetched,
    heroProfile,
    today,
    readiness,
    snapStats,
    weaknesses,
    radarData,
    topicBars,
    roadmaps,
    badges,
    recommendations,
    sessionHistory,
  } = useProfileStats();

  const user = authStore.useStore(s => s.user);

  const handleEdit = () => {
    setView?.('settings');
  };

  const handleContinue = () => {
    onBack?.();
  };

  // Goal toggle — persists to localStorage
  const handleGoalToggle = (goalId, completed) => {
    persistGoalToggle(user?.user_id, goalId, completed);
  };

  // ── Loading State ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto relative z-10 text-[var(--text-primary)]">
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={onBack}
            className="flex items-center gap-2 font-sans font-semibold text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] border border-[var(--border-default)]/60 px-4 py-2.5 rounded-xl hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer shadow-sm"
          >
            <ChevronLeft size={16} /> Back to Mentor
          </button>
        </div>
        <div className="mb-8">
          <span className="section-tag">Academic Profile Station</span>
          <h2 className="section-title">Developer Hub</h2>
        </div>
        <div className="flex flex-col items-center justify-center py-20 gap-4 text-[var(--text-muted)]">
          <RefreshCw size={24} className="animate-spin text-indigo-400" />
          <p className="font-sans text-xs uppercase tracking-widest">Loading profile analytics...</p>
        </div>
      </div>
    );
  }

  // ── Error State ──────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="w-full max-w-4xl mx-auto relative z-10 text-[var(--text-primary)]">
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={onBack}
            className="flex items-center gap-2 font-sans font-semibold text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] border border-[var(--border-default)]/60 px-4 py-2.5 rounded-xl hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer shadow-sm"
          >
            <ChevronLeft size={16} /> Back to Mentor
          </button>
        </div>
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <p className="font-sans text-xs text-rose-400 border border-rose-800/30 bg-rose-950/20 px-4 py-3 rounded-none">
            ⚠ Could not load analytics — backend may be offline. Showing empty state.
          </p>
        </div>
      </div>
    );
  }

  // ── Full Profile ─────────────────────────────────────────────────────────
  return (
    <div className="w-full max-w-4xl mx-auto relative z-10 text-[var(--text-primary)]">
      {/* HEADER CONTROLS */}
      <div className="flex items-center justify-between mb-8">
        <button
          onClick={onBack}
          className="flex items-center gap-2 font-sans font-semibold text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] border border-[var(--border-default)]/60 px-4 py-2.5 rounded-xl hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer shadow-sm"
        >
          <ChevronLeft size={16} /> Back to Mentor
        </button>

        {/* Live sync indicator */}
        <div className="flex items-center gap-2">
          {lastFetched && (
            <span className="font-sans text-[9px] text-[var(--text-muted)] uppercase tracking-wider">
              Synced {new Date(lastFetched).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 font-sans text-[10px] font-semibold text-indigo-400 border border-indigo-500/20 bg-indigo-500/10 px-3 py-1.5 rounded-xl hover:bg-indigo-500/20 transition-all cursor-pointer"
            title="Refresh analytics data"
          >
            <RefreshCw size={11} />
            Refresh
          </button>
        </div>
      </div>

      {/* SECTION TITLE */}
      <div className="mb-8">
        <span className="section-tag">Academic Profile Station</span>
        <h2 className="section-title">Developer Hub</h2>
      </div>

      {/* TOP ROW: TODAY'S ACTIVE TASK PANEL */}
      <div className="mb-8">
        <div className="rounded-2xl overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.03)] border border-[var(--border-default)]/40">
          <CurrentGoals
            today={today}
            onContinue={handleContinue}
            onGoalToggle={handleGoalToggle}
          />
        </div>
      </div>

      {/* SINGLE COLUMN DASHBOARD VERTICAL STACK */}
      <div className="flex flex-col gap-8 w-full">
        {/* STUDENT IDENTITY & QUICK METRICS */}
        <div className="w-full flex flex-col gap-6">
          <HeroCard profile={heroProfile} onEdit={handleEdit} />
        </div>

        {/* STATISTICS, PROGRESS, TIMELINE, ACHIEVEMENTS */}
        <div className="w-full flex flex-col gap-8">
          {/* Learning Snapshot metrics */}
          <SectionCard title="Learning Snapshot" subtitle="Overall study metrics and response indexes" headerBg="bg-neutral-50/50">
            <LearningSnapshot score={readiness.placement_score} stats={snapStats} weaknesses={weaknesses} />
          </SectionCard>

          {/* Current Active Roadmaps */}
          <SectionCard title="Active Learning Roadmaps" subtitle="Placement preparation milestones" headerBg="bg-neutral-50/50">
            <div className="flex flex-col gap-4">
              {roadmaps.map((roadmap, idx) => (
                <div key={idx} className="flex flex-col gap-1.5 border border-[var(--border-default)]/60 p-4 rounded-xl bg-[var(--bg-primary)] shadow-[0_4px_20px_rgb(0,0,0,0.01)] font-sans text-xs text-[var(--text-primary)]">
                  <div className="flex justify-between items-start">
                    <div className="flex flex-col min-w-0">
                      <span className="font-sans font-bold text-xs text-[var(--text-primary)] uppercase leading-tight truncate">{roadmap.title}</span>
                      <span className="text-[var(--text-muted)] text-[9px] mt-0.5 leading-tight truncate">{roadmap.subtitle}</span>
                    </div>
                    <span className="font-semibold text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2.5 py-0.5 rounded-full text-[10px]">{roadmap.progress}%</span>
                  </div>
                  <div className="h-2.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden relative mt-2">
                    <div
                      className="h-full bg-[var(--accent-indigo)] rounded-full transition-all duration-800 ease-out"
                      style={{ width: animateProgress ? `${roadmap.progress}%` : '0%' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Subject Mastery Progress Lists & Radar Chart */}
          <SectionCard title="Knowledge Radar & Rankings" subtitle="Technical depth comparisons across engineering concepts" headerBg="bg-neutral-50/50">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
              <div className="flex justify-center bg-[var(--bg-primary)] p-4 border border-[var(--border-default)]/60 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.02)]">
                <RadarChart data={radarData} />
              </div>

              <div className="flex flex-col gap-4">
                {topicBars.slice(0, 3).map((topic, idx) => {
                  const colors = ['var(--accent-teal)', 'var(--accent-amber)', 'var(--accent-coral)'];
                  return (
                    <SkillBar
                      key={idx}
                      label={topic.subject}
                      percent={topic.percentage}
                      color={colors[idx]}
                    />
                  );
                })}
                {topicBars.length === 0 && (
                  <p className="font-sans text-xs text-[var(--text-muted)] py-2">
                    Complete voice sessions to build your knowledge radar.
                  </p>
                )}
              </div>
            </div>
          </SectionCard>

          {/* Recent Activity Timeline — real conversations and stored DB sessions */}
          <SectionCard title="Recent Study Logs" subtitle="Verbal turn history and conversation nodes" headerBg="bg-neutral-50/50">
            <ActivityTimeline conversations={conversations} sessionHistory={sessionHistory} />
          </SectionCard>

          {/* Badges and Achievement Grid */}
          <SectionCard title="Unlocked Achievements" subtitle="Badges earned through active voice sessions" headerBg="bg-neutral-50/50">
            <AchievementGrid achievements={badges} />
          </SectionCard>

          {/* Dynamic recommendations and next steps */}
          <SectionCard title="Recommended Next Actions" subtitle="Dynamic targets derived from performance logs" headerBg="bg-neutral-50/50">
            <div className="flex flex-col gap-3 font-sans text-xs">
              {recommendations.map((rec, idx) => (
                <div key={idx} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border border-[var(--border-default)]/60 p-4 rounded-xl bg-[var(--bg-primary)] shadow-[0_4px_20px_rgb(0,0,0,0.01)]">
                  <div className="flex items-start gap-2 flex-1">
                    <span className="w-2 h-2 rounded-full bg-[var(--accent-indigo)] mt-1.5 flex-shrink-0" />
                    <span className="leading-relaxed text-[var(--text-secondary)]">{rec.text}</span>
                  </div>
                  <button
                    onClick={handleContinue}
                    className="bg-[var(--bg-primary)] text-[var(--text-primary)] border border-[var(--border-default)]/60 font-sans font-semibold text-xs px-4 py-2 rounded-xl hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer text-center sm:w-auto w-full flex-shrink-0 shadow-sm"
                  >
                    {rec.action}
                  </button>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

export default Profile;
