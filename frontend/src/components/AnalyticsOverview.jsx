import React from 'react';
import { SectionCard } from './Cards/SectionCard';
import { StatCard } from './Cards/StatCard';
import { LineChart } from './Charts/LineChart';
import { ProgressRing } from './Charts/ProgressRing';
import { Heatmap } from './Charts/Heatmap';
import { SkillBar } from './Charts/SkillBar';
import { ChevronLeft, BarChart2, Activity, Calendar, Trophy, MessageSquare, Clock, RefreshCw } from 'lucide-react';
import { FloatingShapes } from './FloatingShapes';
import { useProfileStats } from '../hooks/useProfileStats';

export function AnalyticsOverview({ onBack }) {
  const {
    loading,
    error,
    refresh,
    lastFetched,
    readiness,
    weaknesses,
    topicBars,
    velocityData,
    qualityMetrics,
    tokensData,
    lifetimeSessions,
    rawStats,
    heatmapData,
    sessionHistory,
  } = useProfileStats();

  // ── Derived values from raw stats ────────────────────────────────────────

  // Build heatmap data from real DB heatmapData or velocity fallback
  const heatmap = React.useMemo(() => {
    if (heatmapData && heatmapData.length > 0) {
      return heatmapData.map(h => ({
        date: h.date,
        count: h.count || 0,
      }));
    }
    if (!velocityData || velocityData.length === 0) return [];
    // Fallback: convert weekly velocity → simulated daily data
    const result = [];
    const today = new Date();
    velocityData.slice().reverse().forEach((week, wIdx) => {
      for (let d = 6; d >= 0; d--) {
        const date = new Date(today);
        date.setDate(today.getDate() - (wIdx * 7 + d));
        result.push({
          date: date.toISOString().slice(0, 10),
          count: Math.round(week.value * (Math.random() * 0.4 + 0.8)),
        });
      }
    });
    return result.sort((a, b) => a.date.localeCompare(b.date));
  }, [heatmapData, velocityData]);

  // Build velocity line chart data (last 8 weeks)
  const lineChartData = React.useMemo(() => {
    if (!velocityData || velocityData.length === 0) {
      return [{ label: 'W1', value: 0 }];
    }
    return velocityData.map((v, idx) => ({
      label: `W${idx + 1}`,
      value: parseFloat((v.value * 10).toFixed(1)), // scale to readable range
    }));
  }, [velocityData]);

  // Session difficulty breakdown derived from quality metrics
  const totalTokens = (tokensData.this_week?.in || 0) + (tokensData.this_week?.out || 0);
  const totalLastWeek = (tokensData.last_week?.in || 0) + (tokensData.last_week?.out || 0);
  const specificity = qualityMetrics.specificity || 0;
  const curiosity = qualityMetrics.curiosity || 0;

  // Derive "difficulty" proxy: easy = low specificity, hard = high specificity
  const approxEasy = Math.max(0, Math.round(lifetimeSessions * (1 - specificity) * 0.5));
  const approxHard = Math.max(0, Math.round(lifetimeSessions * specificity * 0.5));
  const approxMedium = Math.max(0, lifetimeSessions - approxEasy - approxHard);
  const totalSolved = Math.max(1, approxEasy + approxMedium + approxHard);
  const pctEasy = (approxEasy / totalSolved) * 100;
  const pctMedium = (approxMedium / totalSolved) * 100;
  const pctHard = (approxHard / totalSolved) * 100;

  // Token efficiency as a percentage
  const efficiencyPct = Math.min(100, Math.round((tokensData.this_week?.efficiency || 0) * 100000));

  // ── Loading / Error states ────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="relative min-h-screen w-full px-4 md:px-8 py-6 bg-[var(--bg-primary)] select-none flex flex-col items-center justify-center gap-4 text-[var(--text-muted)]">
        <RefreshCw size={24} className="animate-spin text-indigo-400" />
        <p className="font-sans text-xs uppercase tracking-widest">Loading analytics data...</p>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen w-full px-4 md:px-8 py-6 bg-[var(--bg-primary)] select-none">
      {/* Background shape animation */}
      <FloatingShapes page="profile" />

      <div className="w-full max-w-4xl mx-auto relative z-10 text-[var(--text-primary)]">

        {/* HEADER CONTROLS */}
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={onBack}
            className="flex items-center gap-2 font-sans font-semibold text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] border border-[var(--border-default)]/60 px-4 py-2.5 rounded-xl hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer shadow-sm hover:translate-x-[-2px]"
          >
            <ChevronLeft size={16} /> Back to Mentor
          </button>

          {/* Live sync indicator + manual refresh */}
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
            {error && (
              <span className="font-sans text-[10px] text-rose-400 border border-rose-800/30 bg-rose-950/20 px-3 py-1">
                ⚠ Backend offline
              </span>
            )}
          </div>
        </div>

        {/* SECTION TITLE */}
        <div className="mb-8">
          <span className="section-tag">Insights Station</span>
          <h2 className="section-title">GitHub Insights & Performance</h2>
        </div>

        {/* SINGLE COLUMN DASHBOARD VERTICAL STACK */}
        <div className="flex flex-col gap-8 w-full">

          {/* GENERAL READINESS PROFILE SUMMARY */}
          <div className="w-full flex flex-col gap-6">

            <SectionCard title="Overall Readiness" subtitle="Weighted placement probability indexes" headerBg="bg-neutral-50/50">
              <div className="flex flex-col items-center gap-6 py-4">
                <div className="flex justify-around w-full">
                  <ProgressRing score={readiness.placement_score} size={90} color="var(--accent-teal)" label="Readiness" />
                  <ProgressRing
                    score={Math.max(0, Math.min(100, Math.round(curiosity * 300)))}
                    size={90}
                    color="var(--accent-coral)"
                    label="Curiosity"
                  />
                </div>

                <div className="w-full border-t border-neutral-150 pt-4 font-sans text-xs text-neutral-500 leading-relaxed flex flex-col gap-2">
                  <div className="flex justify-between">
                    <span>Session specificity:</span>
                    <strong className="text-neutral-800 font-semibold">{Math.round(specificity * 100)}%</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Token efficiency:</span>
                    <strong className="text-neutral-800 font-semibold">{efficiencyPct}%</strong>
                  </div>
                  {readiness.delta !== 0 && (
                    <div className="flex justify-between">
                      <span>Readiness delta:</span>
                      <strong className={`font-semibold ${readiness.delta >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                        {readiness.delta >= 0 ? '+' : ''}{readiness.delta}
                      </strong>
                    </div>
                  )}
                </div>
              </div>
            </SectionCard>

            {/* Quick Insights Cards */}
            <div className="grid grid-cols-2 gap-4">
              <StatCard
                label="Total Sessions"
                value={lifetimeSessions}
                desc="Voice sessions completed"
                icon={MessageSquare}
                colorClass="bg-white"
              />
              <StatCard
                label="Tokens Used"
                value={totalTokens > 1000 ? `${(totalTokens / 1000).toFixed(1)}k` : totalTokens}
                desc="This week's token usage"
                icon={Clock}
                colorClass="bg-white"
              />
            </div>

            <SectionCard title="Priority Focus Areas" subtitle="Analysis of study weaknesses" headerBg="bg-neutral-50/50">
              <div className="font-sans text-xs flex flex-col gap-3">
                <div className="border border-[var(--border-default)]/60 p-4 rounded-xl bg-[var(--bg-tertiary)]/30 flex flex-col shadow-[0_4px_15px_rgb(0,0,0,0.01)] hover:translate-y-[-1px] transition-all">
                  <span className="text-[9.5px] font-bold text-[var(--text-muted)] uppercase tracking-wider">Weakest Concept</span>
                  <span className="font-sans font-bold text-sm text-red-400 mt-1">
                    {weaknesses.weakest_topic || 'No sessions yet'}
                  </span>
                </div>
                <div className="border border-[var(--border-default)]/60 p-4 rounded-xl bg-[var(--bg-tertiary)]/30 flex flex-col shadow-[0_4px_15px_rgb(0,0,0,0.01)] hover:translate-y-[-1px] transition-all">
                  <span className="text-[9.5px] font-bold text-[var(--text-muted)] uppercase tracking-wider">Most Practiced Track</span>
                  <span className="font-sans font-bold text-sm text-[var(--text-primary)] mt-1">
                    {weaknesses.most_practiced_subject || 'Start a session!'}
                  </span>
                </div>
              </div>
            </SectionCard>

          </div>

          {/* HEATMAP, VELOCITY CURVES, PROGRESS LIST */}
          <div className="w-full flex flex-col gap-6">

            {/* Session Consistency Heatmap */}
            <SectionCard title="Consistency Calendar" subtitle="Commitment frequency of voice tutoring sessions" headerBg="bg-neutral-50/50">
              <div className="py-2">
                {heatmap.length > 0 ? (
                  <Heatmap data={heatmap} />
                ) : (
                  <p className="font-sans text-xs text-[var(--text-muted)] py-4 text-center opacity-60">
                    Complete sessions to build your consistency calendar.
                  </p>
                )}
              </div>
            </SectionCard>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">

              {/* Session difficulty breakdown */}
              <SectionCard title="Interaction Depth" subtitle="Question complexity breakdown" headerBg="bg-neutral-50/50">
                <div className="flex flex-col justify-between h-full font-sans text-xs">
                  <div className="flex flex-col gap-2 py-4">
                    <div className="h-4.5 rounded-full overflow-hidden flex shadow-[inset_0_1px_3px_rgba(0,0,0,0.05)] bg-[var(--bg-tertiary)]">
                      <div className="h-full bg-[var(--accent-teal)] transition-all duration-500 border-r border-white/20" style={{ width: `${pctEasy}%` }} title="Basic" />
                      <div className="h-full bg-[var(--accent-amber)] transition-all duration-500 border-r border-white/20" style={{ width: `${pctMedium}%` }} title="Intermediate" />
                      <div className="h-full bg-[var(--accent-coral)] transition-all duration-500" style={{ width: `${pctHard}%` }} title="Advanced" />
                    </div>

                    <div className="flex justify-between items-center text-[10.5px] mt-2.5 font-medium text-[var(--text-secondary)]">
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-teal)]" /> Basic ({approxEasy})</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-amber)]" /> Mid ({approxMedium})</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--accent-coral)]" /> Deep ({approxHard})</span>
                    </div>
                  </div>

                  <div className="border-t border-[var(--border-default)] pt-2.5 text-center text-[10px] font-semibold text-[var(--text-muted)]">
                    Total Sessions Analysed: {lifetimeSessions}
                  </div>
                </div>
              </SectionCard>

              {/* Knowledge Velocity Line Chart */}
              <SectionCard title="Learning Velocity" subtitle="Concept depth per week trend" headerBg="bg-neutral-50/50">
                <div className="py-2">
                  <LineChart
                    data={lineChartData}
                    height={100}
                    color="var(--blue-200)"
                  />
                </div>
                {lineChartData.length === 1 && lineChartData[0].value === 0 && (
                  <p className="font-sans text-[10px] text-[var(--text-muted)] text-center opacity-60 mt-1">
                    Complete sessions to see velocity trend.
                  </p>
                )}
              </SectionCard>

            </div>

            {/* Subject Area Mastery Ratings — from live fingerprint */}
            <SectionCard title="Subject Area Mastery Ratings" subtitle="Competency percentages by core discipline module" headerBg="bg-neutral-50/50">
              <div className="flex flex-col gap-4 py-2">
                {topicBars.length > 0 ? (
                  topicBars.map((topic, idx) => {
                    const colors = ['var(--accent-amber)', 'var(--accent-coral)', 'var(--accent-teal)', 'var(--blue-400)'];
                    return (
                      <SkillBar
                        key={idx}
                        label={topic.subject}
                        percent={topic.percentage}
                        color={colors[idx % colors.length]}
                      />
                    );
                  })
                ) : (
                  <p className="font-sans text-xs text-[var(--text-muted)] py-2 opacity-60">
                    Start voice sessions to build your mastery ratings.
                  </p>
                )}
              </div>
            </SectionCard>

          </div>

        </div>

      </div>
    </div>
  );
}

export default AnalyticsOverview;
