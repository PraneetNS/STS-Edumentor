import React, { useState, useEffect } from 'react';
import CodeStrategy from './CodeStrategy';
import MermaidStrategy from './MermaidStrategy';
import RoadmapStrategy from './RoadmapStrategy';
import ComparisonTableStrategy from './ComparisonTableStrategy';
import ChecklistStrategy from './ChecklistStrategy';
import { extractVisualBlocks } from '../../../../utils/visualBlockExtractor';
import { PanelsTopLeft, Compass, ClipboardList, Code, Table, Cpu, HelpCircle } from 'lucide-react';

const strategyMap = {
  code: CodeStrategy,
  roadmap: RoadmapStrategy,
  workflow: RoadmapStrategy,
  table: ComparisonTableStrategy,
  checklist: ChecklistStrategy,
  mermaid: MermaidStrategy,
};

const iconMap = {
  code: Code,
  roadmap: Compass,
  workflow: Compass,
  table: Table,
  checklist: ClipboardList,
  mermaid: Cpu,
};

export default function DisplayPanel({ activeMessage }) {
  const [blocks, setBlocks] = useState([]);
  const [activeBlockId, setActiveBlockId] = useState('');

  // Extract blocks whenever the active message changes
  useEffect(() => {
    if (!activeMessage || !activeMessage.text) {
      setBlocks([]);
      setActiveBlockId('');
      return;
    }

    const parsedBlocks = extractVisualBlocks(activeMessage.text);
    setBlocks(parsedBlocks);
    
    if (parsedBlocks.length > 0) {
      // If a new block comes in or if activeBlockId is not in the new blocks, set the last one active
      const exists = parsedBlocks.some((b) => b.id === activeBlockId);
      if (!exists) {
        // Default to the first block
        setActiveBlockId(parsedBlocks[0].id);
      }
    } else {
      setActiveBlockId('');
    }
  }, [activeMessage?.text, activeMessage?.id]);

  const activeBlock = blocks.find((b) => b.id === activeBlockId);

  // Render Strategy selection (Strategy Pattern)
  const renderStrategy = () => {
    if (!activeBlock) return null;
    const StrategyComponent = strategyMap[activeBlock.type] || CodeStrategy;
    return <StrategyComponent block={activeBlock} />;
  };

  // If no blocks are available, show a helpful onboarding placeholder
  if (blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl select-none">
        <PanelsTopLeft size={36} className="text-zinc-700 mb-4 stroke-1 animate-pulse" />
        <h3 className="text-sm font-semibold text-zinc-300 mb-1">Interactive Display Workspace</h3>
        <p className="text-xs text-zinc-500 max-w-[280px] leading-relaxed">
          When EDI shares code snippets, architectural diagrams, tables, or roadmaps, they will appear here interactively in real time.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden gap-3">
      {/* Block selector tabs (if multiple blocks exist) */}
      {blocks.length > 1 && (
        <div className="flex items-center gap-1.5 p-1 bg-zinc-900/80 border border-zinc-800 rounded-lg overflow-x-auto select-none shrink-0">
          {blocks.map((block) => {
            const Icon = iconMap[block.type] || HelpCircle;
            const isActive = block.id === activeBlockId;
            return (
              <button
                key={block.id}
                onClick={() => setActiveBlockId(block.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  isActive
                    ? 'bg-zinc-800 text-white shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                }`}
              >
                <Icon size={12} className={isActive ? 'text-indigo-400' : ''} />
                <span>{block.title}</span>
                {block.isStreaming && (
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Strategy render viewport */}
      <div className="flex-1 overflow-hidden min-h-0">
        {renderStrategy()}
      </div>
    </div>
  );
}
