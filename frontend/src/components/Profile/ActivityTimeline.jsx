import React from 'react';
import { TimelineCard } from '../Cards/TimelineCard';
import { CheckCircle, BookOpen, FileText, Code2, ShieldAlert } from 'lucide-react';

export function ActivityTimeline() {
  // Mock timeline activities grouped by time sections
  const timelineGroups = [
    {
      group: 'Today',
      items: [
        { time: '11:15 AM', title: 'Solved Binary Trees balancing nodes', desc: 'Covered AVL rotations, insert/delete properties with EDI.', icon: Code2, color: 'bg-[var(--yellow)]' },
        { time: '09:30 AM', title: 'Asked about OOP polymorphism', desc: 'Explored static vs dynamic dispatch compile resolution mechanisms.', icon: BookOpen, color: 'bg-[var(--lavender)]' }
      ]
    },
    {
      group: 'Yesterday',
      items: [
        { time: '04:10 PM', title: 'Generated placements mock resume', desc: 'Synthesised active coding project logs into single-page PDF.', icon: FileText, color: 'bg-[var(--mint)]' },
        { time: '11:00 AM', title: 'Solved 12 DSA practice problems', desc: 'Graph traversals, topological sorting, DFS and BFS recursion.', icon: CheckCircle, color: 'bg-[var(--yellow)]' }
      ]
    },
    {
      group: 'This Week',
      items: [
        { time: '2 Days Ago', title: 'Mock placement voice interview', desc: 'Completed round 1 technical interview covering networking basics.', icon: CheckCircle, color: 'bg-[var(--lavender)]' },
        { time: '4 Days Ago', title: 'Roadmap roadmap_4 updated', desc: 'Transitioned study plan status to candidate level.', icon: BookOpen, color: 'bg-[var(--mint)]' }
      ]
    }
  ];

  return (
    <div className="flex flex-col gap-6 select-none font-mono">
      {timelineGroups.map((groupObj, idx) => (
        <div key={idx} className="flex flex-col gap-3">
          <h4 className="font-sans font-extrabold text-[10px] uppercase text-black/45 tracking-wider mb-2">
            {groupObj.group}
          </h4>
          
          <div className="flex flex-col">
            {groupObj.items.map((item, itemIdx) => {
              const isLast = idx === timelineGroups.length - 1 && itemIdx === groupObj.items.length - 1;
              return (
                <TimelineCard
                  key={itemIdx}
                  time={item.time}
                  title={item.title}
                  desc={item.desc}
                  icon={item.icon}
                  colorClass={item.color}
                  isLast={isLast}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
