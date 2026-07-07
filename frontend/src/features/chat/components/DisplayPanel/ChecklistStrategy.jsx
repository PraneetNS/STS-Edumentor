import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ClipboardList, CheckCircle } from 'lucide-react';

export default function ChecklistStrategy({ block }) {
  const [items, setItems] = useState([]);
  const [subheading, setSubheading] = useState('');

  useEffect(() => {
    const lines = block.content.split('\n');
    const parsedItems = [];
    let foundSubheading = '';

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      // Handle Markdown headings
      if (trimmed.startsWith('#')) {
        foundSubheading = trimmed.replace(/^#+\s*/, '');
        return;
      }

      const checkboxMatch = trimmed.match(/^[-*]\s+\[([ xX])\]\s+(.*)/);
      const bulletMatch = trimmed.match(/^[-*]\s+(.*)/);

      if (checkboxMatch) {
        parsedItems.push({
          id: `item-${parsedItems.length}`,
          text: checkboxMatch[2],
          completed: checkboxMatch[1].toLowerCase() === 'x',
        });
      } else if (bulletMatch) {
        parsedItems.push({
          id: `item-${parsedItems.length}`,
          text: bulletMatch[1],
          completed: false,
        });
      } else {
        // Plain line
        parsedItems.push({
          id: `item-${parsedItems.length}`,
          text: trimmed,
          completed: false,
        });
      }
    });

    setItems(parsedItems);
    setSubheading(foundSubheading);
  }, [block.content]);

  const toggleItem = (id) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, completed: !item.completed } : item))
    );
  };

  const completedCount = items.filter((i) => i.completed).length;
  const progressPercent = items.length > 0 ? Math.round((completedCount / items.length) * 100) : 0;

  return (
    <div className="flex flex-col h-full bg-[#161619] rounded-xl border border-zinc-800/80 overflow-hidden font-sans shadow-lg select-text">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 bg-[#1e1e24] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2.5">
          <ClipboardList size={18} className="text-indigo-400" />
          <span className="font-bold text-sm text-zinc-100">{block.title || 'Checklist Summary'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded border border-emerald-900/30">
          <CheckCircle size={12} />
          <span>{completedCount}/{items.length} Done</span>
        </div>
      </div>

      {/* Progress Bar */}
      {items.length > 0 && (
        <div className="bg-zinc-900/80 border-b border-zinc-800 px-5 py-3 flex items-center gap-4 select-none">
          <div className="flex-1 bg-zinc-850 h-2 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-indigo-500 to-emerald-400 h-full rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs font-bold font-mono text-zinc-300 w-10 text-right">
            {progressPercent}%
          </span>
        </div>
      )}

      {/* Checklist items */}
      <div className="flex-1 overflow-y-auto p-5 select-text">
        {subheading && (
          <h4 className="text-[11px] font-bold uppercase tracking-wider text-indigo-400 mb-3.5 select-none pl-1">
            {subheading}
          </h4>
        )}
        {items.length === 0 ? (
          <p className="text-zinc-500 text-sm text-center mt-8">No checklist items parsed.</p>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                onClick={() => toggleItem(item.id)}
                className={`flex items-start gap-4 p-3.5 rounded-xl border cursor-pointer transition-all duration-200 ${
                  item.completed
                    ? 'bg-zinc-950/40 border-zinc-900/90 hover:bg-zinc-950/50'
                    : 'bg-zinc-900/40 border-zinc-800/90 hover:bg-zinc-900/60 hover:border-zinc-700/80 shadow-xs'
                }`}
              >
                {/* Custom Checkbox */}
                <div className="relative flex items-center justify-center mt-0.5">
                  <input
                    type="checkbox"
                    checked={item.completed}
                    readOnly
                    className="sr-only"
                  />
                  <div className={`w-4 h-4 rounded border flex items-center justify-center transition-all ${
                    item.completed
                      ? 'bg-indigo-600 border-indigo-500'
                      : 'border-zinc-700 hover:border-zinc-500 bg-zinc-900'
                  }`}>
                    {item.completed && (
                      <motion.svg
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="w-2.5 h-2.5 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={4}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </motion.svg>
                    )}
                  </div>
                </div>

                <span className={`text-[13px] leading-relaxed select-text transition-all ${
                  item.completed
                    ? 'text-zinc-500 line-through opacity-60'
                    : 'text-zinc-200 font-medium'
                }`}>
                  {item.text}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
