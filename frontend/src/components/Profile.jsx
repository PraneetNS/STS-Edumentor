import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RadarChart } from './RadarChart';
import { authStore } from '../stores/authStore';
import { Award, Zap, RefreshCw, ChevronLeft } from 'lucide-react';

export function Profile({ onBack }) {
  const user = authStore.useStore(s => s.user);
  const stats = authStore.useStore(s => s.profileStats);
  const fetchStats = authStore.getState().fetchStats;
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadData = async () => {
    setIsRefreshing(true);
    await fetchStats();
    setIsRefreshing(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-slate-400 gap-4" style={{ fontFamily: 'var(--font-mono)' }}>
        <RefreshCw className="animate-spin text-orange-500" size={24} />
        <div>LOGGING INTO SECURE API & COMPUTING METRICS...</div>
      </div>
    );
  }

  const { readiness, fingerprint, velocity, phase, quality, tokens, lifetime_sessions } = stats;

  // Initials for avatar fallback
  const initials = user?.display_name
    ? user.display_name.split(' ').map(n => n[0]).join('').toUpperCase()
    : 'U';

  // Arc calculations for Readiness Score
  const score = readiness.score || 0;
  const arcRadius = 40;
  const circumference = 2 * Math.PI * arcRadius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  // Sparkline coordinates for Knowledge Velocity
  const sparkWidth = 240;
  const sparkHeight = 60;
  const values = (velocity || []).map(v => v.value);
  const minVal = Math.min(...values, 0);
  const maxVal = Math.max(...values, 10);
  const valRange = maxVal - minVal || 1;

  const points = (velocity || []).map((v, i) => {
    const x = (i / (velocity.length - 1 || 1)) * (sparkWidth - 20) + 10;
    const y = sparkHeight - ((v.value - minVal) / valRange) * (sparkHeight - 20) - 10;
    return `${x},${y}`;
  });

  return (
    <div className="profile-page-container max-w-5xl mx-auto px-4 py-8 select-none text-slate-200" style={{ fontFamily: 'var(--font-mono)' }}>
      {/* Header Controls */}
      <div className="flex items-center justify-between mb-8">
        <button onClick={onBack} className="flex items-center gap-2 text-xs uppercase text-slate-400 hover:text-orange-500 border border-slate-800 hover:border-orange-500 px-3 py-1.5 rounded transition-all">
          <ChevronLeft size={14} /> Back to Mentor
        </button>
        <button onClick={loadData} className="flex items-center gap-2 text-xs uppercase text-slate-400 hover:text-orange-500 border border-slate-800 hover:border-orange-500 px-3 py-1.5 rounded transition-all">
          <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} /> Sync Stats
        </button>
      </div>

      {/* ZONE 1: Identity Strip */}
      <div className="border border-slate-800 bg-[#0F1117]/85 p-6 rounded mb-6 flex flex-col md:flex-row items-center justify-between gap-6 relative overflow-hidden">
        {/* Blueprint background grid lines */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.015)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:15px_15px] pointer-events-none" />

        <div className="flex items-center gap-4 z-10">
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt={user.display_name} className="w-16 h-16 rounded border border-orange-500/30 object-cover" />
          ) : (
            <div className="w-16 h-16 bg-[#181C26] border border-orange-500/40 rounded flex items-center justify-center text-lg font-bold text-orange-500">
              {initials}
            </div>
          )}
          <div>
            <h2 className="text-lg font-bold text-white leading-tight">{user?.display_name || 'Student'}</h2>
            <div className="text-xs text-slate-400 mt-1">{user?.email}</div>
            <div className="text-[10px] text-slate-500 mt-1">MEMBER SINCE {new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long' })}</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 z-10">
          <div className="border border-orange-500/20 bg-orange-950/20 px-3 py-1.5 rounded flex items-center gap-2">
            <Award size={14} className="text-orange-500" />
            <div>
              <div className="text-[9px] text-slate-400">LEARNING PHASE</div>
              <div className="text-xs font-bold text-white uppercase">{phase.current}</div>
            </div>
          </div>

          <div className="border border-slate-800 bg-slate-900/35 px-3 py-1.5 rounded flex items-center gap-2">
            <Zap size={14} className="text-orange-500" />
            <div>
              <div className="text-[9px] text-slate-400">LIFETIME SESSIONS</div>
              <div className="text-xs font-bold text-white">{lifetime_sessions} SESSIONS</div>
            </div>
          </div>
        </div>
      </div>

      {/* ZONE 2: Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        
        {/* Metric 1: Readiness Score */}
        <div className="border border-slate-800 bg-[#0F1117]/85 p-6 rounded flex flex-col justify-between">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-4">Engineering Readiness</div>
          <div className="flex items-center justify-center py-2 relative">
            <svg width="100" height="100" viewBox="0 0 100 100" className="-rotate-90">
              <circle cx="50" cy="50" r={arcRadius} fill="none" stroke="rgba(255, 107, 0, 0.08)" strokeWidth="8" />
              <motion.circle
                cx="50"
                cy="50"
                r={arcRadius}
                fill="none"
                stroke="#FF6B00"
                strokeWidth="8"
                strokeDasharray={circumference}
                strokeDashoffset={circumference}
                animate={{ strokeDashoffset }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center text-xl font-bold text-white">
              {score}
            </div>
          </div>
          <div className="text-center mt-4">
            <div className={`text-xs font-bold ${readiness.delta >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {readiness.delta >= 0 ? '+' : ''}{readiness.delta} WoW Delta
            </div>
            <div className="text-[9px] text-slate-500 mt-1">Calculated across active days, followup rate, and discipline variety</div>
          </div>
        </div>

        {/* Metric 2: Knowledge Velocity */}
        <div className="border border-slate-800 bg-[#0F1117]/85 p-6 rounded flex flex-col justify-between">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-4">Knowledge Velocity</div>
          <div className="flex justify-center items-center py-4 bg-[#08090C] border border-slate-900 rounded">
            <svg width={sparkWidth} height={sparkHeight} className="overflow-visible">
              {points.length > 1 && (
                <>
                  <polyline
                    fill="none"
                    stroke="rgba(255, 107, 0, 0.15)"
                    strokeWidth="1.5"
                    points={points.join(' ')}
                  />
                  <motion.path
                    d={`M ${points[0].replace(',', ' ')} ${points.slice(1).map(p => `L ${p.replace(',', ' ')}`).join(' ')}`}
                    fill="none"
                    stroke="#FF6B00"
                    strokeWidth="2.5"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: 1.0, ease: 'easeOut' }}
                  />
                  {points.map((p, idx) => {
                    const [x, y] = p.split(',');
                    return (
                      <circle
                        key={idx}
                        cx={x}
                        cy={y}
                        r="3.5"
                        fill="#0F1117"
                        stroke="#FF6B00"
                        strokeWidth="1.5"
                        title={`${velocity[idx].label}: ${velocity[idx].value} turns`}
                      />
                    );
                  })}
                </>
              )}
            </svg>
          </div>
          <div className="text-center mt-4">
            <div className="text-xs text-slate-300">
              Avg: {values.length > 0 ? (values.reduce((a,b)=>a+b,0)/values.length).toFixed(1) : 0} Turns/Concept
            </div>
            <div className="text-[9px] text-slate-500 mt-1">Lower average turns per concept indicates faster absorption velocity</div>
          </div>
        </div>

        {/* Metric 3: Token Usage */}
        <div className="border border-slate-800 bg-[#0F1117]/85 p-6 rounded flex flex-col justify-between">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-4">Token Efficiency</div>
          <div className="flex flex-col gap-4 py-2">
            <div>
              <div className="flex justify-between text-[9px] text-slate-400 mb-1">
                <span>THIS WEEK</span>
                <span>{(tokens.this_week.in + tokens.this_week.out).toLocaleString()} TOKENS</span>
              </div>
              <div className="h-3 bg-slate-900 border border-slate-800 rounded-sm overflow-hidden relative">
                <motion.div
                  className="h-full bg-orange-600"
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, ((tokens.this_week.in + tokens.this_week.out) / (Math.max(tokens.this_week.in + tokens.this_week.out, tokens.last_week.in + tokens.last_week.out, 1))) * 100)}%` }}
                  transition={{ duration: 0.8 }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-[9px] text-slate-400 mb-1">
                <span>LAST WEEK</span>
                <span>{(tokens.last_week.in + tokens.last_week.out).toLocaleString()} TOKENS</span>
              </div>
              <div className="h-3 bg-slate-900 border border-slate-800 rounded-sm overflow-hidden relative">
                <motion.div
                  className="h-full bg-slate-700"
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, ((tokens.last_week.in + tokens.last_week.out) / (Math.max(tokens.this_week.in + tokens.this_week.out, tokens.last_week.in + tokens.last_week.out, 1))) * 100)}%` }}
                  transition={{ duration: 0.8 }}
                />
              </div>
            </div>
          </div>
          <div className="text-center mt-4">
            <div className="text-xs text-orange-500 font-bold">
              Efficiency: {(tokens.this_week.efficiency * 1000).toFixed(2)} pts
            </div>
            <div className="text-[9px] text-slate-500 mt-1">Calculated as useful turns divided by total input/output tokens</div>
          </div>
        </div>

        {/* Metric 4: Curiosity Index */}
        <div className="border border-slate-800 bg-[#0F1117]/85 p-6 rounded flex flex-col justify-between">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-4">Curiosity Index</div>
          <div className="text-center py-2">
            <div className="text-4xl font-bold text-white font-mono mt-2">
              {Math.round(quality.curiosity * 100)}%
            </div>
            <div className={`text-[10px] mt-1 font-bold ${quality.curiosity_delta >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {quality.curiosity_delta >= 0 ? '+' : ''}{Math.round(quality.curiosity_delta * 100)}% 30d Delta
            </div>
          </div>
          <div className="text-center mt-4">
            <div className="text-xs text-slate-400">
              Specificity: {Math.round(quality.specificity * 100)}%
            </div>
            <div className="text-[9px] text-slate-500 mt-1">Ratio of self-initiated queries not responding to suggested mentor questions</div>
          </div>
        </div>

      </div>

      {/* ZONE 3: Discipline Fingerprint */}
      <div className="border border-slate-800 bg-[#0F1117]/85 rounded relative overflow-hidden">
        {/* Blueprint background grid lines */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,107,0,0.012)_1px,transparent_1px),linear-gradient(90deg,rgba(255,107,0,0.012)_1px,transparent_1px)] bg-[size:20px_20px] pointer-events-none" />

        <div className="p-6 border-b border-slate-800 z-10 relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h3 className="text-white font-bold text-sm">DISCIPLINE FINGERPRINT</h3>
            <p className="text-[10px] text-slate-500 mt-0.5">Tactical depth ratio across engineering categories</p>
          </div>
          <div className="text-xs text-orange-500 font-bold bg-orange-950/20 px-2 py-1 rounded border border-orange-500/10">
            NEXT STAGE TARGET: {phase.next.toUpperCase()}
          </div>
        </div>

        <div className="flex justify-center items-center py-6 z-10 relative">
          <RadarChart data={fingerprint} />
        </div>
      </div>
    </div>
  );
}
