import React from 'react';
import { User, Sparkles, Volume2, BookOpen, Bell, Shield, Link2, AlertTriangle } from 'lucide-react';

export function SettingsSidebar({ activeTab = 'account', onTabChange }) {
  const tabs = [
    { id: 'account', label: 'Account', icon: User },
    { id: 'voice', label: 'Voice settings', icon: Volume2 },
    { id: 'learning', label: 'Learning Preferences', icon: BookOpen },
    { id: 'notifications', label: 'Notification Settings', icon: Bell },
    { id: 'privacy', label: 'Privacy & Security', icon: Shield },
    { id: 'connected', label: 'Connected Accounts', icon: Link2 },
    { id: 'danger', label: 'Danger Zone', icon: AlertTriangle, colorClass: 'text-red-500 hover:bg-red-500/10 hover:text-red-600' }
  ];

  return (
    <div className="flex flex-col gap-1 w-full select-none font-sans">
      <div className="font-sans font-bold text-[10.5px] uppercase text-[var(--text-muted)] px-4 mb-2.5 tracking-wider">
        System Settings
      </div>
      
      <div className="flex flex-col gap-1">
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`w-full text-left flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer hover:translate-x-[2px] ${
                isActive 
                  ? 'bg-[var(--accent-indigo-glow)] text-[var(--accent-indigo)] font-bold border-l-2 border-[var(--accent-indigo)] pl-3 rounded-l-none' 
                  : tab.colorClass || 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]/60'
              }`}
            >
              <Icon size={14} className="flex-shrink-0" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
