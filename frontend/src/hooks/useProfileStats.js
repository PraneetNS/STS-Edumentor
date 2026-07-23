/**
 * useProfileStats
 *
 * Central hook for the Profile and Analytics views.
 * Fetches GET /api/profile/stats once per session (cached in authStore),
 * then derives all secondary computed values from the raw API response:
 *   - heroProfile  : identity data merged from authStore.user
 *   - readiness    : score + breakdown
 *   - fingerprint  : radar chart values (cse, mech, eee, ...)
 *   - topicBars    : skill bar data derived from fingerprint
 *   - badges       : computed achievement unlock states
 *   - roadmaps     : 3 learning roadmaps with live progress %
 *   - goals        : daily goal items (persisted per user in localStorage)
 *   - recommendations : dynamic next-action cards
 *   - velocityData : weekly trend for sparkline charts
 *   - phase        : current learning phase label
 *   - qualityMetrics: specificity, curiosity, token efficiency
 *   - loading / error
 */

import { useEffect, useState, useCallback } from 'react';
import { authStore } from '../stores/authStore';

// ─── Helpers ────────────────────────────────────────────────────────────────

/**
 * Returns a greeting string based on current hour.
 */
function buildGreeting(displayName) {
  const hour = new Date().getHours();
  const name = displayName ? displayName.split(' ')[0] : 'there';
  if (hour < 12) return `Good Morning, ${name} 👋`;
  if (hour < 17) return `Good Afternoon, ${name} 👋`;
  return `Good Evening, ${name} 👋`;
}

/**
 * Compute streak: how many consecutive days (ending today) the user had sessions.
 * We derive this from velocity data (last 8 weeks) which gives per-week activity.
 * Falls back to checking lifetime_sessions > 0 → at least a 1-day streak.
 */
function computeStreak(stats) {
  if (!stats || !stats.lifetime_sessions) return 0;
  // A simple heuristic: if there's data this week, streak >= 1
  const thisWeek = stats.tokens?.this_week;
  if (!thisWeek || (thisWeek.in === 0 && thisWeek.out === 0)) return 0;
  // Velocity weeks where value > 0
  const activeWeeks = (stats.velocity || []).filter(v => v.value > 0).length;
  return Math.min(activeWeeks * 2, 30); // rough estimate, capped at 30
}

/**
 * Map fingerprint scores (0.0–1.0) to topic distribution bars (0–100%).
 */
function fingerprintToTopicBars(fingerprint) {
  if (!fingerprint) return [];
  const labelMap = {
    cse:      'Computer Science',
    mech:     'Mechanical Eng',
    eee:      'Electrical Eng',
    civil:    'Civil Eng',
    chemical: 'Chemical Eng',
    aerospace:'Aerospace Eng',
  };
  return Object.entries(fingerprint).map(([key, val]) => ({
    subject: labelMap[key] || key.toUpperCase(),
    percentage: Math.round(val * 100),
  })).sort((a, b) => b.percentage - a.percentage);
}

/**
 * Compute which badges are unlocked based on live stats.
 */
function computeBadges(stats) {
  const lifetime = stats?.lifetime_sessions || 0;
  const streak = computeStreak(stats);
  const fp = stats?.fingerprint || {};
  const thisWeekTokens = (stats?.tokens?.this_week?.in || 0) + (stats?.tokens?.this_week?.out || 0);
  const approxQuestions = lifetime * 3; // rough: ~3 turns per session

  return [
    {
      id: 'b_first_session',
      name: 'First Session',
      icon: '🚀',
      description: 'Completed your very first EduMentor voice session.',
      unlocked: lifetime >= 1,
    },
    {
      id: 'b_7day_streak',
      name: '7 Day Streak',
      icon: '🔥',
      description: 'Practiced engineering voice sessions for 7 consecutive days.',
      unlocked: streak >= 7,
    },
    {
      id: 'b_30day_streak',
      name: '30 Day Streak',
      icon: '⚡',
      description: 'Practiced engineering voice sessions for 30 consecutive days.',
      unlocked: streak >= 30,
    },
    {
      id: 'b_100questions',
      name: '100 Questions',
      icon: '💯',
      description: 'Asked over 100 deep technical queries to EDI.',
      unlocked: approxQuestions >= 100,
    },
    {
      id: 'b_dsa_explorer',
      name: 'DSA Explorer',
      icon: '🌳',
      description: 'Deeply explored Data Structures & Algorithms with EDI.',
      unlocked: (fp.cse || 0) >= 0.5,
    },
    {
      id: 'b_top_consistency',
      name: 'Top Consistency',
      icon: '📅',
      description: 'Maintained consistent sessions for multiple weeks.',
      unlocked: (stats?.velocity || []).filter(v => v.value > 0).length >= 4,
    },
    {
      id: 'b_ai_learner',
      name: 'AI Learner',
      icon: '🤖',
      description: 'Explored foundational concepts of AI and system engineering.',
      unlocked: lifetime >= 5,
    },
    {
      id: 'b_debug_master',
      name: 'Debug Master',
      icon: '🐛',
      description: 'Solved 10+ debugging and coding challenges with EDI.',
      unlocked: (fp.cse || 0) >= 0.4 && lifetime >= 10,
    },
    {
      id: 'b_system_architect',
      name: 'System Architect',
      icon: '🌐',
      description: 'Achieved strong depth in System Design and architecture concepts.',
      unlocked: (fp.cse || 0) >= 0.75,
    },
    {
      id: 'b_placement_ready',
      name: 'Placement Ready',
      icon: '🎓',
      description: 'Completed mock placement tests with excellent grade scores.',
      unlocked: (stats?.readiness?.score || 0) >= 80,
    },
    {
      id: 'b_speed_learner',
      name: 'Speed Learner',
      icon: '⏱️',
      description: 'Demonstrated high concept velocity — learned rapidly per session.',
      unlocked: (stats?.quality?.curiosity || 0) >= 0.5,
    },
  ];
}

/**
 * Build 3 learning roadmaps with live progress derived from fingerprint + phase.
 */
function computeRoadmaps(stats) {
  const fp = stats?.fingerprint || {};
  const phase = stats?.phase?.current || 'foundation-building';
  const readScore = stats?.readiness?.score || 0;

  const cseProgress = Math.min(100, Math.round((fp.cse || 0) * 120));
  const interviewProgress = Math.min(100, Math.round(readScore * 0.9));
  const systemProgress = Math.min(100, Math.round((fp.aerospace || 0) * 150 + (fp.cse || 0) * 40));

  return [
    {
      title: 'Data Structures & Algorithms',
      subtitle: `Phase: ${phase} — Building depth in problem-solving`,
      progress: cseProgress,
    },
    {
      title: 'Placement Technical Interviewing',
      subtitle: `Target: Score 80%+ on voice session trials`,
      progress: interviewProgress,
    },
    {
      title: 'Distributed Systems & Architecture',
      subtitle: `Target: Map microservices and system design paradigms`,
      progress: systemProgress,
    },
  ];
}

/**
 * Build recommended next actions from live quality & phase data.
 */
function computeRecommendations(stats) {
  const phase = stats?.phase?.current || 'foundation-building';
  const curiosity = stats?.quality?.curiosity || 0;
  const specificity = stats?.quality?.specificity || 0;
  const fp = stats?.fingerprint || {};

  // Find weakest discipline
  const sorted = Object.entries(fp).sort((a, b) => a[1] - b[1]);
  const weakestKey = sorted[0]?.[0] || 'cse';
  const weakestLabel = {
    cse: 'CS Fundamentals',
    mech: 'Mechanical Engineering',
    eee: 'Electrical Engineering',
    civil: 'Civil Engineering',
    chemical: 'Chemical Engineering',
    aerospace: 'Aerospace Engineering',
  }[weakestKey] || 'your weakest subject';

  const recs = [];

  if (phase === 'foundation-building' || phase === 'placement-prep') {
    recs.push({
      text: `Focus on ${weakestLabel}: spend at least 2 voice sessions diving deep into core concepts.`,
      action: 'Start Session',
    });
  }

  if (curiosity < 0.3) {
    recs.push({
      text: 'Ask more follow-up questions to build conceptual depth — your curiosity score is below target.',
      action: 'Resume Learning',
    });
  } else {
    recs.push({
      text: 'Great curiosity score! Continue asking probing questions and challenge EDI with edge cases.',
      action: 'Continue Chatting',
    });
  }

  if (specificity < 0.25) {
    recs.push({
      text: 'Try asking more specific, targeted questions — detailed queries yield better mentor responses.',
      action: 'Try a Quiz',
    });
  } else {
    recs.push({
      text: `You are in ${phase.replace('-', ' ')} phase — consider advancing to the next level of complexity.`,
      action: `Advance Phase`,
    });
  }

  // Always keep 3 recommendations
  while (recs.length < 3) {
    recs.push({
      text: 'Complete at least one voice session today to maintain your consistency streak.',
      action: 'Start Session',
    });
  }

  return recs.slice(0, 3);
}

/**
 * Build daily goal items. These are derived from phase + stats.
 * Checkbox state is persisted in localStorage keyed to the user's ID.
 */
function buildDailyGoals(stats, userId) {
  const phase = stats?.phase?.current || 'foundation-building';
  const fp = stats?.fingerprint || {};

  const phaseGoalMap = {
    'foundation-building': [
      { id: 'g1', label: 'Complete one voice session covering a core CS concept', completed: false },
      { id: 'g2', label: 'Ask 5 follow-up questions to build conceptual depth', completed: false },
      { id: 'g3', label: 'Review session summary and take notes on weak areas', completed: false },
      { id: 'g4', label: 'Explore one new discipline outside your primary focus', completed: false },
    ],
    'placement-prep': [
      { id: 'g1', label: 'Solve 3 DSA problems with voice-guided explanations', completed: false },
      { id: 'g2', label: 'Practice 1 mock technical interview question with EDI', completed: false },
      { id: 'g3', label: 'Review system design caching levels (Redis vs Memcached)', completed: false },
      { id: 'g4', label: 'Revise OOP design patterns (Strategy & Factory)', completed: false },
    ],
    'interview-mode': [
      { id: 'g1', label: 'Complete a full mock interview session with EDI', completed: false },
      { id: 'g2', label: 'Practice behavioral question narration (STAR method)', completed: false },
      { id: 'g3', label: 'Code review: optimize one solution for time complexity', completed: false },
      { id: 'g4', label: 'Simulate system design round: design a URL shortener', completed: false },
    ],
    'post-offer': [
      { id: 'g1', label: 'Explore onboarding topics for your target company stack', completed: false },
      { id: 'g2', label: 'Read one system design case study and discuss with EDI', completed: false },
      { id: 'g3', label: 'Review advanced data structures: tries, segment trees', completed: false },
      { id: 'g4', label: 'Practice leadership principles and cross-team communication', completed: false },
    ],
  };

  const baseGoals = phaseGoalMap[phase] || phaseGoalMap['foundation-building'];

  // Restore persisted checkbox state from localStorage
  const storageKey = `edumentor_goals_${userId || 'anon'}_${new Date().toDateString()}`;
  let savedState = {};
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) savedState = JSON.parse(raw);
  } catch (_) {}

  return baseGoals.map(g => ({
    ...g,
    completed: savedState[g.id] ?? g.completed,
  }));
}

// ─── Hook ───────────────────────────────────────────────────────────────────

/** Stale time: re-fetch if data is older than 60 seconds */
const STALE_MS = 60_000;

export function useProfileStats() {
  const user = authStore.useStore(s => s.user);
  const profileStats = authStore.useStore(s => s.profileStats);
  const sessionHistory = authStore.useStore(s => s.sessionHistory);
  const heatmapData = authStore.useStore(s => s.heatmapData);

  const fetchStats = authStore.getState().fetchStats;
  const fetchSessions = authStore.getState().fetchSessions;
  const fetchHeatmap = authStore.getState().fetchHeatmap;

  const [loading, setLoading] = useState(!profileStats);
  const [error, setError] = useState(null);
  const [lastFetched, setLastFetched] = useState(null);

  const doFetch = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      // Fetch all three concurrently
      await Promise.all([
        fetchStats(),
        fetchSessions(),
        fetchHeatmap(),
      ]);
      setLastFetched(Date.now());
    } catch (e) {
      setError(e?.message || 'Failed to load stats');
    } finally {
      setLoading(false);
    }
  }, [fetchStats, fetchSessions, fetchHeatmap]);

  // ── Initial fetch on mount (always fresh — ignore stale cache) ──
  useEffect(() => {
    let cancelled = false;
    // Show spinner only if no cached data yet; otherwise update silently
    const showLoading = !authStore.getState().profileStats;
    const run = async () => {
      if (showLoading) setLoading(true);
      setError(null);
      try {
        await Promise.all([
          fetchStats(),
          fetchSessions(),
          fetchHeatmap(),
        ]);
        if (!cancelled) setLastFetched(Date.now());
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Failed to load stats');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-refresh every 60 seconds while the hook is mounted ──
  useEffect(() => {
    const interval = setInterval(() => {
      doFetch(false); // silent refresh — no spinner
    }, STALE_MS);
    return () => clearInterval(interval);
  }, [doFetch]);

  const stats = profileStats;
  const userId = user?.user_id;
  const streak = computeStreak(stats);

  // ── Hero profile (merge auth user + live stats)
  const heroProfile = {
    display_name: user?.display_name || 'Student',
    email: user?.email || '',
    initials: (user?.display_name || 'S').slice(0, 2).toUpperCase(),
    avatar_url: user?.avatar_url || null,
    student_id: userId ? `STU-${userId.toString().slice(0, 8).toUpperCase()}` : 'STU-ID',
    branch: 'Engineering',
    college: 'EduMentor Platform',
    year: stats?.phase?.current
      ? stats.phase.current.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      : 'Foundation Building',
    current_goal: stats?.phase?.next
      ? `Next Phase: ${stats.phase.next.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`
      : 'Target: Engineering Excellence',
    current_streak: streak,
  };

  // ── Today panel
  const today = {
    greeting: buildGreeting(user?.display_name),
    goals: buildDailyGoals(stats, userId),
    estimated_time_mins: 90,
  };

  // ── Readiness + stats snapshot
  const readiness = {
    placement_score: stats?.readiness?.score ?? 0,
    delta: stats?.readiness?.delta ?? 0,
  };

  const snapStats = {
    study_hours: stats
      ? Math.round(
          ((stats.tokens?.this_week?.in || 0) + (stats.tokens?.this_week?.out || 0)) / 2000 * 10
        ) / 10
      : 0,
    average_response_delay_sec: stats?.quality
      ? (2 + (1 - (stats.quality.specificity || 0)) * 3).toFixed(1)
      : 0,
    weekly_improvement_percentage: stats?.readiness?.delta
      ? Math.abs(Math.round(stats.readiness.delta))
      : 0,
  };

  const weaknesses = {
    weakest_topic: (() => {
      if (!stats?.fingerprint) return 'No sessions yet';
      const sorted = Object.entries(stats.fingerprint).sort((a, b) => a[1] - b[1]);
      const key = sorted[0]?.[0] || 'cse';
      const label = {
        cse: 'CS Fundamentals', mech: 'Mechanical Engineering',
        eee: 'Electrical Engineering', civil: 'Civil Engineering',
        chemical: 'Chemical Engineering', aerospace: 'Aerospace Engineering',
      };
      return label[key] || key;
    })(),
    most_practiced_subject: (() => {
      if (!stats?.fingerprint) return 'Start a session!';
      const sorted = Object.entries(stats.fingerprint).sort((a, b) => b[1] - a[1]);
      const key = sorted[0]?.[0] || 'cse';
      const label = {
        cse: 'CS & DSA', mech: 'Mechanical Engineering',
        eee: 'Electrical Engineering', civil: 'Civil Engineering',
        chemical: 'Chemical Engineering', aerospace: 'Aerospace Engineering',
      };
      return label[key] || key;
    })(),
  };

  // ── Radar fingerprint (already in correct shape from API)
  const radarData = stats?.fingerprint || {
    cse: 0, mech: 0, eee: 0, civil: 0, chemical: 0, aerospace: 0,
  };

  // ── Topic bars derived from fingerprint
  const topicBars = fingerprintToTopicBars(stats?.fingerprint);

  // ── Active roadmaps
  const roadmaps = computeRoadmaps(stats);

  // ── Badges
  const badges = computeBadges(stats);

  // ── Recommendations
  const recommendations = computeRecommendations(stats);

  // ── Quality metrics for analytics
  const qualityMetrics = stats?.quality || {
    specificity: 0,
    curiosity: 0,
    specificity_delta: 0,
    curiosity_delta: 0,
  };

  const velocityData = stats?.velocity || [];
  const phase = stats?.phase || { current: 'foundation-building', next: 'placement-prep' };
  const lifetimeSessions = stats?.lifetime_sessions || 0;
  const tokensData = stats?.tokens || { this_week: { in: 0, out: 0, efficiency: 0 }, last_week: { in: 0, out: 0, efficiency: 0 } };

  return {
    loading,
    error,
    lastFetched,
    refresh: () => doFetch(false),
    // Identity
    heroProfile,
    today,
    // Analytics
    readiness,
    snapStats,
    weaknesses,
    radarData,
    topicBars,
    // Derived content
    roadmaps,
    badges,
    recommendations,
    // Raw advanced metrics
    qualityMetrics,
    velocityData,
    phase,
    lifetimeSessions,
    tokensData,
    // Raw stats for analytics overview
    rawStats: stats,
    // DB session history & heatmap (new)
    sessionHistory: sessionHistory || [],
    heatmapData: heatmapData || [],
  };
}

/**
 * Persist goal checkbox toggle to localStorage.
 * Call this when the user checks/unchecks a goal.
 */
export function persistGoalToggle(userId, goalId, completed) {
  const storageKey = `edumentor_goals_${userId || 'anon'}_${new Date().toDateString()}`;
  try {
    const raw = localStorage.getItem(storageKey);
    const saved = raw ? JSON.parse(raw) : {};
    saved[goalId] = completed;
    localStorage.setItem(storageKey, JSON.stringify(saved));
  } catch (_) {}
}
