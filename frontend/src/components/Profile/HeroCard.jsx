import React from 'react';
import { motion } from 'framer-motion';
import { Award, Flame, User, Mail, School, BookOpen } from 'lucide-react';

export function HeroCard({ profile = {}, onEdit }) {
  const { display_name, email, initials, branch, college, year, current_goal, current_streak, student_id } = profile;
  
  const initialChar = display_name ? display_name[0].toUpperCase() : 'U';

  return (
    <div className="border border-[var(--border-default)]/60 bg-[var(--bg-primary)]/80 backdrop-blur-md p-6 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.03)] relative overflow-hidden flex flex-col select-none text-[var(--text-primary)]">
      {/* Student ID sticker */}
      <div className="absolute top-3.5 right-3.5 bg-[var(--bg-tertiary)]/60 font-sans text-[9px] font-bold text-[var(--text-muted)] px-3 py-1 rounded-full border border-[var(--border-default)]/40">
        {student_id || 'STU-ID'}
      </div>

      <div className="flex flex-col items-center">
        {/* Circular Avatar with hover rotate animation and subtle glow */}
        <motion.div 
          className="w-24 h-24 bg-[var(--bg-primary)] border border-indigo-500/10 rounded-full p-1 flex items-center justify-center shadow-[0_8px_25px_rgba(99,102,241,0.08)] overflow-hidden mb-4 cursor-pointer relative z-10"
          whileHover={{ rotate: 15, scale: 1.03 }}
          transition={{ type: 'spring', stiffness: 200, damping: 12 }}
        >
          <div className="w-full h-full bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-full flex items-center justify-center font-sans font-bold text-3.5xl text-white">
            {initials || initialChar}
          </div>
        </motion.div>

        {/* Identity Texts */}
        <h3 className="font-sans font-bold text-base text-[var(--text-primary)] tracking-tight text-center mt-1 truncate w-full">
          {display_name || 'Student Candidate'}
        </h3>
        <p className="font-sans text-xs text-[var(--text-muted)] mt-1.5 flex items-center gap-1.5">
          <Mail size={12} className="text-indigo-400" /> {email || 'student@university.edu'}
        </p>

        <div className="w-full border-t border-[var(--border-default)]/50 my-4.5" />

        {/* Institution Details */}
        <div className="w-full flex flex-col gap-3 font-sans text-xs text-[var(--text-secondary)]">
          <div className="flex items-start gap-2.5">
            <School size={14} className="mt-0.5 flex-shrink-0 text-[var(--text-muted)]" />
            <span className="leading-tight font-medium">{college || 'Engineering Institute'}</span>
          </div>
          <div className="flex items-start gap-2.5">
            <BookOpen size={14} className="mt-0.5 flex-shrink-0 text-[var(--text-muted)]" />
            <span className="leading-tight font-medium">{branch} ({year})</span>
          </div>
          <div className="flex items-start gap-2.5">
            <Award size={14} className="mt-0.5 flex-shrink-0 text-indigo-400" />
            <span className="leading-tight font-semibold text-indigo-400">{current_goal}</span>
          </div>
        </div>

        {/* Streak Flame */}
        <div className="w-full mt-5 flex items-center justify-between bg-[var(--bg-tertiary)]/50 border border-[var(--border-default)]/40 px-4 py-3 rounded-xl shadow-[0_4px_15px_rgb(0,0,0,0.01)]">
          <div className="flex items-center gap-2">
            <Flame size={16} className="text-orange-500 animate-pulse" fill="currentColor" />
            <span className="font-sans font-bold text-xs text-[var(--text-primary)]">Streak: {current_streak || 0} Days</span>
          </div>
          <span className="font-sans text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-wider">Keep it up!</span>
        </div>

        {/* Edit Button */}
        <button 
          onClick={onEdit}
          className="w-full mt-4 bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-default)]/60 font-sans font-semibold py-2.5 rounded-xl shadow-sm hover:shadow-md transition-all cursor-pointer text-xs text-center hover:translate-y-[-1px]"
        >
          Edit Profile Details
        </button>
      </div>
    </div>
  );
}
