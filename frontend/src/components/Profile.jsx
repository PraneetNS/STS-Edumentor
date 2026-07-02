import React, { useEffect, useState } from 'react';

import { HeroCard } from './Profile/HeroCard';

import { LearningSnapshot } from './Profile/LearningSnapshot';

import { CurrentGoals } from './Profile/CurrentGoals';

import { AchievementGrid } from './Profile/AchievementGrid';

import { ActivityTimeline } from './Profile/ActivityTimeline';

import { SectionCard } from './Cards/SectionCard';

import { SkillBar } from './Charts/SkillBar';

import { RadarChart } from './RadarChart';

import { ChevronLeft, Compass, Bookmark, TrendingUp } from 'lucide-react';

import { FloatingShapes } from './FloatingShapes';



// Import local JSON mock databases

import mockUser from '../data/user.json';

import mockAnalytics from '../data/analytics.json';

import mockAchievements from '../data/achievements.json';



export function Profile({ onBack, conversations = [], setView }) {

  const [animateProgress, setAnimateProgress] = useState(false);



  useEffect(() => {

    const timer = setTimeout(() => setAnimateProgress(true), 150);

    return () => clearTimeout(timer);

  }, []);



  const handleEdit = () => {

    setView?.('settings');

  };



  const handleContinue = () => {

    onBack?.();

  };



  // Resolve readiness indexes and subject mastery lists

  const { profile, today } = mockUser;

  const { readiness, stats, weaknesses, topic_distribution } = mockAnalytics;

  const { badges } = mockAchievements;



  // Derive active focus items

  const activeRoadmaps = [

    { title: 'Data Structures & Algorithms', subtitle: 'Target: Solve 50 Graph & Trees challenges', progress: 82 },

    { title: 'Placement Technical Interviewing', subtitle: 'Target: Score 80%+ on mock voice trials', progress: 55 },

    { title: 'Distributed Systems & Architecture', subtitle: 'Target: Map microservices paradigms', progress: 32 }

  ];



  const recommendations = [

    { text: 'Complete Binary Trees: review deletion cases and node pointer resets.', action: 'Resume DSA' },

    { text: 'Practice Graphs: implement Dijkstra and topological sorting traversal.', action: 'Solve Problem' },

    { text: 'Revise OOP principles: define virtual tables and runtime bindings.', action: 'Review Quiz' }

  ];



  return (

    <div className="relative w-full min-h-screen px-4 md:px-8 py-6 bg-white select-none overflow-y-auto" style={{ maxHeight: '100vh' }}>

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

          <span className="section-tag">Academic Profile Station</span>

          <h2 className="section-title">Developer Hub</h2>

        </div>



        {/* TOP ROW: TODAY'S ACTIVE TASK PANEL (COL-SPAN-12) */}

        <div className="mb-8">

          <div className="border border-neutral-250 rounded-2xl overflow-hidden shadow-sm">

            <CurrentGoals today={today} onContinue={handleContinue} />

          </div>

        </div>



        {/* 12-COLUMN DASHBOARD GRID LAYOUT */}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">

          

          {/* SIDEBAR: STUDENT IDENTITY & QUICK METRICS (COL-SPAN-4) */}

          <div className="lg:col-span-4 flex flex-col gap-6 lg:sticky lg:top-8">

            <HeroCard profile={profile} onEdit={handleEdit} />

          </div>



          {/* MAIN COLUMN: STATISTICS, PROGRESS, TIMELINE, ACHIEVEMENTS (COL-SPAN-8) */}

          <div className="lg:col-span-8 flex flex-col gap-8">

            

            {/* Learning Snapshot metrics */}

            <SectionCard title="Learning Snapshot" subtitle="Overall study metrics and response indexes" headerBg="bg-neutral-50/50">

              <LearningSnapshot score={readiness.placement_score} stats={stats} weaknesses={weaknesses} />

            </SectionCard>



            {/* Current Active Roadmaps */}

            <SectionCard title="Active Learning Roadmaps" subtitle="Placement preparation milestones" headerBg="bg-neutral-50/50">

              <div className="flex flex-col gap-4">

                {activeRoadmaps.map((roadmap, idx) => (

                  <div key={idx} className="flex flex-col gap-1.5 border border-neutral-200 p-4 rounded-xl bg-white shadow-sm font-sans text-xs">

                    <div className="flex justify-between items-start">

                      <div className="flex flex-col min-w-0">

                        <span className="font-sans font-extrabold text-xs text-black uppercase leading-tight truncate">{roadmap.title}</span>

                        <span className="text-black/50 text-[9px] mt-0.5 leading-tight truncate">{roadmap.subtitle}</span>

                      </div>

                      <span className="font-semibold text-blue-700 bg-blue-50 border border-blue-100 px-2.5 py-0.5 rounded-full text-[10px]">{roadmap.progress}%</span>

                    </div>

                    <div className="h-2 bg-neutral-100 border border-neutral-200 rounded-full overflow-hidden relative mt-2">

                      <div 

                        className="h-full bg-blue-500 transition-all duration-800 ease-out"

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

                <div className="flex justify-center bg-white p-2 border border-neutral-200 rounded-xl shadow-sm">

                  <RadarChart data={mockAnalytics.radar_fingerprint} />

                </div>

                <div className="flex flex-col gap-4">

                  {topic_distribution.slice(0, 3).map((topic, idx) => {

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

                </div>

              </div>

            </SectionCard>



            {/* Recent Activity Timeline */}

            <SectionCard title="Recent Study Logs" subtitle="Verbal turn history and roadmap generation nodes" headerBg="bg-neutral-50/50">

              <ActivityTimeline />

            </SectionCard>



            {/* Badges and Achievement Grid */}

            <SectionCard title="Unlocked Achievements" subtitle="Badges earned through active voice sessions" headerBg="bg-neutral-50/50">

              <AchievementGrid achievements={badges} />

            </SectionCard>



            {/* Dynamic recommendations and next steps */}

            <SectionCard title="Recommended Next Actions" subtitle="Dynamic targets derived from performance logs" headerBg="bg-neutral-50/50">

              <div className="flex flex-col gap-3 font-sans text-xs">

                {recommendations.map((rec, idx) => (

                  <div key={idx} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border border-neutral-200 p-4 rounded-xl bg-white shadow-sm">

                    <div className="flex items-start gap-2 flex-1">

                      <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 flex-shrink-0" />

                      <span className="leading-relaxed text-black/75">{rec.text}</span>

                    </div>

                    <button 

                      onClick={handleContinue}

                      className="bg-white text-neutral-700 border border-neutral-200 font-sans font-semibold text-xs px-3.5 py-2 rounded-xl hover:bg-neutral-50 transition-all cursor-pointer text-center sm:w-auto w-full flex-shrink-0 shadow-sm"

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

    </div>

  );

}

export default Profile;

