import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Circle, ArrowRight, BookOpen, Compass } from 'lucide-react';

export default function RoadmapStrategy({ block }) {
  const [steps, setSteps] = useState([]);
  const [expandedIndex, setExpandedIndex] = useState(0);
  const [subheading, setSubheading] = useState('');

  useEffect(() => {
    // Parse roadmap steps from block content
    const parsedSteps = [];
    const lines = block.content.split('\n');
    let currentStep = null;
    let foundSubheading = '';

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      // Handle Markdown headings
      if (trimmed.startsWith('#')) {
        foundSubheading = trimmed.replace(/^#+\s*/, '');
        return;
      }

      // Check if line represents a new step (e.g., "1. Topic" or "- [x] Topic" or "* [ ] Topic")
      const checklistMatch = trimmed.match(/^[-*]\s+\[([ xX])\]\s+(?:(\d+)\.\s+)?(.*)/);
      const plainStepMatch = trimmed.match(/^(?:(\d+)\.\s+)?(.*)/);

      if (checklistMatch) {
        if (currentStep) parsedSteps.push(currentStep);
        const completed = checklistMatch[1].toLowerCase() === 'x';
        const num = checklistMatch[2] || (parsedSteps.length + 1).toString();
        const title = checklistMatch[3];
        currentStep = { number: num, title, completed, details: [] };
      } else if (trimmed.startsWith('1.') || trimmed.match(/^\d+\./)) {
        if (currentStep) parsedSteps.push(currentStep);
        const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
        const num = numMatch ? numMatch[1] : (parsedSteps.length + 1).toString();
        const title = numMatch ? numMatch[2] : trimmed;
        currentStep = { number: num, title, completed: false, details: [] };
      } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        // Bullet list details under the current step
        if (currentStep) {
          currentStep.details.push(trimmed.replace(/^[-*]\s+/, ''));
        }
      } else {
        // Plain text details
        if (currentStep) {
          currentStep.details.push(trimmed);
        } else {
          // If no step created yet, create a default first step
          currentStep = {
            number: '1',
            title: trimmed,
            completed: false,
            details: []
          };
        }
      }
    });

    if (currentStep) parsedSteps.push(currentStep);
    
    // Auto-mark first few as completed or set initial state
    setSteps(parsedSteps);
    setSubheading(foundSubheading);
  }, [block.content]);

  const toggleStepCompleted = (index, e) => {
    e.stopPropagation();
    setSteps((prev) =>
      prev.map((step, idx) => (idx === index ? { ...step, completed: !step.completed } : step))
    );
  };

  return (
    <div className="flex flex-col h-full bg-[#161619] rounded-xl border border-zinc-800/80 overflow-hidden font-sans shadow-lg select-text">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-5 py-4 bg-[#1e1e24] border-b border-zinc-800 select-none">
        <Compass size={18} className="text-indigo-400" />
        <span className="font-bold text-sm text-zinc-100">{block.title || 'Learning Roadmap'}</span>
      </div>

      {/* Main steps container */}
      <div className="flex-1 overflow-y-auto p-5 select-text relative">
        {subheading && (
          <h4 className="text-[11px] font-bold uppercase tracking-wider text-indigo-400 mb-4 ml-3 select-none">
            {subheading}
          </h4>
        )}
        {steps.length === 0 ? (
          <p className="text-zinc-500 text-xs text-center mt-8">No roadmap milestones parsed.</p>
        ) : (
          <div className="relative pl-6 border-l-2 border-zinc-800/80 ml-3 space-y-6 py-2">
            {steps.map((step, idx) => {
              const isExpanded = expandedIndex === idx;
              const isCompleted = step.completed;

              return (
                <div key={idx} className="relative group cursor-pointer" onClick={() => setExpandedIndex(isExpanded ? -1 : idx)}>
                  {/* Step Node indicator on the timeline line */}
                  <div
                    onClick={(e) => toggleStepCompleted(idx, e)}
                    className={`absolute -left-[35px] top-1 w-6 h-6 rounded-full flex items-center justify-center transition-all border duration-300 z-10 hover:scale-110 ${
                      isCompleted
                        ? 'bg-emerald-950 border-emerald-500 text-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                        : 'bg-zinc-900 border-zinc-700 text-zinc-500 hover:border-indigo-500 hover:text-indigo-400'
                    }`}
                  >
                    {isCompleted ? <CheckCircle2 size={13} /> : <Circle size={11} />}
                  </div>

                  {/* Card Content */}
                  <div className={`p-3.5 rounded-lg border transition-all duration-300 ${
                    isExpanded 
                      ? 'bg-zinc-900/60 border-zinc-700 shadow-md' 
                      : 'bg-zinc-900/20 border-zinc-800/80 hover:border-zinc-800 hover:bg-zinc-900/40'
                  }`}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded ${
                          isCompleted ? 'bg-emerald-950/50 text-emerald-500' : 'bg-zinc-800 text-zinc-400'
                        }`}>
                          STEP {step.number}
                        </span>
                        <h4 className={`text-xs font-semibold tracking-tight transition-colors ${
                          isCompleted ? 'text-zinc-400 line-through' : 'text-zinc-200'
                        } group-hover:text-white`}>
                          {step.title}
                        </h4>
                      </div>
                      <ArrowRight size={12} className={`text-zinc-500 transition-transform ${isExpanded ? 'rotate-90 text-indigo-400' : ''}`} />
                    </div>

                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="mt-3 pt-3 border-t border-zinc-800/50 text-[11px] text-zinc-400 leading-relaxed space-y-2">
                            {step.details.length === 0 ? (
                              <p className="italic text-zinc-500">No additional milestone description provided.</p>
                            ) : (
                              step.details.map((detail, dIdx) => (
                                <div key={dIdx} className="flex gap-2 items-start">
                                  <BookOpen size={11} className="text-indigo-400 mt-0.5 shrink-0" />
                                  <span>{detail}</span>
                                </div>
                              ))
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
