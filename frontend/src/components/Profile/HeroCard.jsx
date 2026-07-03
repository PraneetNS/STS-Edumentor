import React from 'react';
import { motion } from 'framer-motion';
import { Award, Flame, User, Mail, School, BookOpen } from 'lucide-react';

export function HeroCard({ profile = {}, onEdit }) {
  const { display_name, email, initials, branch, college, year, current_goal, current_streak, student_id } = profile;
  
  const initialChar = display_name ? display_name[0].toUpperCase() : 'U';

  return (
    <div className="border border-[var(--border-default)] bg-[var(--bg-primary)] p-6 rounded-none shadow-sm relative overflow-hidden flex flex-col select-none text-[var(--text-primary)]">
      {/* Student ID sticker */}
      <div className="absolute top-3 right-3 bg-[var(--bg-tertiary)] font-sans text-[9px] font-semibold text-[var(--text-muted)] px-2.5 py-0.5 rounded-none">
        {student_id || 'STU-ID'}
      </div>

      <div className="flex flex-col items-center">
        {/* Large Avatar with hover rotate animation */}
        <motion.div 
          className="w-24 h-24 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-none flex items-center justify-center shadow-sm overflow-hidden mb-4 cursor-pointer relative z-10"
          whileHover={{ rotate: 10, scale: 1.02 }}
          transition={{ type: 'spring', stiffness: 200, damping: 12 }}
        >
          <div className="w-full h-full bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center font-sans font-semibold text-3xl text-white">
            {initials || initialChar}
          </div>
        </motion.div>

        {/* Identity Texts */}
        <h3 className="font-sans font-bold text-lg text-[var(--text-primary)] tracking-tight text-center uppercase truncate w-full">
          {display_name || 'Student Candidate'}
        </h3>
        <p className="font-sans text-xs text-[var(--text-muted)] mt-1 flex items-center gap-1.5">
          <Mail size={12} /> {email || 'student@university.edu'}
        </p>

        <div className="w-full border-t border-[var(--border-default)] my-4" />

        {/* Institution Details */}
        <div className="w-full flex flex-col gap-2.5 font-sans text-xs text-[var(--text-secondary)]">
          <div className="flex items-start gap-2">
            <School size={14} className="mt-0.5 flex-shrink-0 text-[var(--text-tertiary)]" />
            <span className="leading-tight">{college || 'Engineering Institute'}</span>
          </div>
          <div className="flex items-start gap-2">
            <BookOpen size={14} className="mt-0.5 flex-shrink-0 text-[var(--text-tertiary)]" />
            <span className="leading-tight">{branch} ({year})</span>
          </div>
          <div className="flex items-start gap-2">
            <Award size={14} className="mt-0.5 flex-shrink-0 text-indigo-400" />
            <span className="leading-tight font-semibold text-indigo-400">{current_goal}</span>
          </div>
        </div>

        {/* Streak Flame */}
        <div className="w-full mt-4 flex items-center justify-between bg-[var(--bg-tertiary)] border border-[var(--border-default)] px-4 py-2.5 rounded-none shadow-sm">
          <div className="flex items-center gap-2">
            <Flame size={16} className="text-orange-500 animate-pulse" fill="currentColor" />
            <span className="font-sans font-bold text-xs text-[var(--text-primary)]">Streak: {current_streak || 0} Days</span>
          </div>
          <span className="font-sans text-[9px] font-medium text-[var(--text-muted)] uppercase">Keep it up!</span>
        </div>

        {/* Edit Button */}
        <button 
          onClick={onEdit}
          className="w-full mt-4 bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-default)] font-sans font-semibold py-2.5 rounded-none shadow-sm transition-all cursor-pointer text-xs text-center"
        >
          Edit Profile Details
        </button>
      </div>
    </div>
  );
}
