import React, { useState } from 'react';
import { SettingsSidebar } from './Settings/SettingsSidebar';
import { SettingsPanel } from './Settings/SettingsPanel';
import { authStore } from '../stores/authStore';
import { ChevronLeft } from 'lucide-react';
import { FloatingShapes } from './FloatingShapes';
import mockSettings from '../data/settings.json';

export function SettingsView({ onBack }) {
  const [activeTab, setActiveTab] = useState('account');
  const logout = authStore.getState().logout;

  const handleSave = (updated) => {
    console.log('[Settings] Saving changes:', updated);
  };

  return (
    <div className="relative min-h-screen w-full px-4 md:px-8 py-6 bg-white select-none overflow-y-auto">
      {/* Background shape animation */}
      <FloatingShapes page="profile" />

      <div className="w-full relative z-10">
        
        {/* HEADER CONTROLS */}
        <div className="flex items-center justify-between mb-8">
          <button 
            onClick={onBack} 
            className="flex items-center gap-2 font-sans font-semibold text-xs text-neutral-600 bg-white border border-neutral-200 px-4 py-2.5 rounded-full hover:bg-neutral-50 transition-all cursor-pointer shadow-sm"
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
              initialSettings={mockSettings}
              onSave={handleSave} 
              onLogout={logout} 
            />
          </div>
        </div>

      </div>
    </div>
  );
}
export default SettingsView;
