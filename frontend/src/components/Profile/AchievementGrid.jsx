import React from 'react';
import { Badge } from '../Common/Badge';

export function AchievementGrid({ achievements = [] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4 select-none">
      {achievements.map((badge, idx) => (
        <Badge
          key={badge.id || idx}
          name={badge.name}
          icon={badge.icon}
          desc={badge.description}
          unlocked={badge.unlocked}
        />
      ))}
    </div>
  );
}
