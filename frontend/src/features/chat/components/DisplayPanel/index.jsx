import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Code, HelpCircle, Inbox, Layers } from 'lucide-react';

import { CodeStrategy } from './CodeStrategy';
import { ChecklistStrategy } from './ChecklistStrategy';
import { TableStrategy } from './TableStrategy';
import { TimelineStrategy } from './TimelineStrategy';
import { MermaidStrategy } from './MermaidStrategy';

import { extractVisualBlocks } from '../../../../utils/visualBlockExtractor';

// Strategy registry mapping block types to renderer strategies
const STRATEGIES = {
  code: CodeStrategy,
  checklist: ChecklistStrategy,
  table: TableStrategy,
  roadmap: TimelineStrategy,
  workflow: TimelineStrategy,
  mermaid: MermaidStrategy,
};

export function DisplayPanel({ messages = [] }) {
  // Extract all visual blocks from the conversation history
  const allVisualBlocks = useMemo(() => {
    const blocks = [];
    messages.forEach((msg) => {
      if (msg.role === 'assistant') {
        const msgBlocks = extractVisualBlocks(msg.text);
        blocks.push(...msgBlocks);
      }
    });
    return blocks;
  }, [messages]);

  // Select the last visual block to render by default
  const activeBlock = allVisualBlocks[allVisualBlocks.length - 1];

  const RendererComponent = useMemo(() => {
    if (!activeBlock) return null;
    return STRATEGIES[activeBlock.type] || CodeStrategy;
  }, [activeBlock]);

  return (
    <div className="flex flex-col h-full bg-zinc-50/50 dark:bg-zinc-950/20 border-l border-zinc-200 dark:border-zinc-800 relative select-none">
      {activeBlock ? (
        <div className="flex-1 flex flex-col overflow-hidden p-6">
          {/* Header Metadata */}
          <div className="flex items-center gap-2 mb-4 shrink-0">
            <Layers className="text-indigo-500" size={16} />
            <span className="text-xs font-bold text-zinc-400 dark:text-zinc-500 uppercase tracking-widest">
              Active Workspace Output
            </span>
          </div>

          {/* Active Renderer strategy */}
          <div className="flex-1 overflow-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeBlock.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.25, type: 'tween' }}
                className="h-full"
              >
                {RendererComponent ? (
                  <RendererComponent block={activeBlock} />
                ) : (
                  <div className="p-4 bg-yellow-50 text-yellow-800 rounded-lg text-xs">
                    Unsupported strategy type: {activeBlock.type}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      ) : (
        /* Empty State */
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center gap-4 select-none">
          <div className="w-12 h-12 rounded-full border border-zinc-200 dark:border-zinc-800 flex items-center justify-center bg-white dark:bg-zinc-900 shadow-xs text-zinc-400">
            <Inbox size={20} />
          </div>
          <div className="flex flex-col gap-1 max-w-xs">
            <h4 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
              Interactive Workspace
            </h4>
            <p className="text-xs text-zinc-500 leading-relaxed">
              When Edi generates roadmaps, code snippets, checklist summaries, or tables, they will automatically populate here.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
