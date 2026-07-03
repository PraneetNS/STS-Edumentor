import React, { useState } from 'react';
import { SettingsSidebar } from './Settings/SettingsSidebar';
import { SettingsPanel } from './Settings/SettingsPanel';
import { authStore } from '../stores/authStore';
import { ChevronLeft } from 'lucide-react';
import { FloatingShapes } from './FloatingShapes';
import mockSettings from '../data/settings.json';

const STORAGE_KEY = 'edumentor_settings';

export function SettingsView({ onBack }) {
  const [activeTab, setActiveTab] = useState('account');
  const logout = authStore.getState().logout;

  const [currentSettings, setCurrentSettings] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.warn('[Settings] Failed to load from localStorage:', e);
    }
    return mockSettings;
  });

  const handleSave = (updated) => {
    console.log('[Settings] Saving changes:', updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      setCurrentSettings(updated);
      window.dispatchEvent(new CustomEvent('edumentor_settings_saved', { detail: updated }));
    } catch (e) {
      console.error('[Settings] Failed to save to localStorage:', e);
    }
  };

  return (
    <div className="w-full relative z-10 text-[var(--text-primary)]">
        
        {/* HEADER CONTROLS */}
        <div className="flex items-center justify-between mb-8">
          <button 
            onClick={onBack} 
            className="flex items-center gap-2 font-sans font-semibold text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] border border-[var(--border-default)] px-4 py-2.5 rounded-none hover:bg-[var(--bg-tertiary)] transition-all cursor-pointer shadow-sm"
          >
            <ChevronLeft size={16} /> Back to Mentor
          </button>
        </div>

        {/* SECTION TITLE */}
        <div className="mb-8">
          <span className="section-tag">User Settings</span>
          <h2 className="section-title">Preference Controls</h2>
        </div>

        {/* SETTINGS VIEW PANEL SPLIT */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Settings Sidebar */}
          <div className="md:col-span-4 lg:col-span-3">
            <SettingsSidebar activeTab={activeTab} onTabChange={setActiveTab} />
          </div>

          {/* Settings Content Area */}
          <div className="md:col-span-8 lg:col-span-9 flex flex-col min-h-[70vh]">
            <SettingsPanel 
              activeTab={activeTab} 
              initialSettings={currentSettings}
              onSave={handleSave} 
              onLogout={logout} 
            />
          </div>
        </div>

    </div>
  );
}
export default SettingsView;
