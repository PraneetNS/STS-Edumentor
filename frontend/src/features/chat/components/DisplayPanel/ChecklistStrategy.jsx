import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ClipboardList, CheckCircle } from 'lucide-react';

export default function ChecklistStrategy({ block }) {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const lines = block.content.split('\n');
    const parsedItems = [];

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

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
  }, [block.content]);

  const toggleItem = (id) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, completed: !item.completed } : item))
    );
  };

  const completedCount = items.filter((i) => i.completed).length;
  const progressPercent = items.length > 0 ? Math.round((completedCount / items.length) * 100) : 0;

  return (
    <div className="flex flex-col h-full bg-[#121214] rounded-lg border border-zinc-800 overflow-hidden font-sans">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#18181B] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2">
          <ClipboardList size={16} className="text-indigo-400" />
          <span className="font-semibold text-xs text-zinc-200">{block.title || 'Checklist Summary'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-900/30">
          <CheckCircle size={10} />
          <span>{completedCount}/{items.length} Done</span>
        </div>
      </div>

      {/* Progress Bar */}
      {items.length > 0 && (
        <div className="bg-zinc-900/60 border-b border-zinc-800 px-4 py-2.5 flex items-center gap-3 select-none">
          <div className="flex-1 bg-zinc-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-indigo-500 to-emerald-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-[10px] font-bold font-mono text-zinc-400 w-8 text-right">
            {progressPercent}%
          </span>
        </div>
      )}

      {/* Checklist items */}
      <div className="flex-1 overflow-y-auto p-4 select-text">
        {items.length === 0 ? (
          <p className="text-zinc-500 text-xs text-center mt-8">No checklist items parsed.</p>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                onClick={() => toggleItem(item.id)}
                className={`flex items-start gap-3 p-2.5 rounded-lg border cursor-pointer transition-all duration-200 ${
                  item.completed
                    ? 'bg-zinc-950/20 border-zinc-900/80 hover:bg-zinc-950/30'
                    : 'bg-zinc-900/10 border-zinc-800/80 hover:bg-zinc-900/30 hover:border-zinc-800'
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

                <span className={`text-xs leading-relaxed select-text transition-all ${
                  item.completed
                    ? 'text-zinc-500 line-through opacity-70'
                    : 'text-zinc-300'
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
