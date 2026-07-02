import React, { useState } from 'react';
import { Save, LogOut, Trash2, ShieldCheck, Download, AlertTriangle } from 'lucide-react';

export function SettingsPanel({ activeTab = 'account', initialSettings = {}, onSave, onLogout }) {
  const [settings, setSettings] = useState(initialSettings);
  const [isSaved, setIsSaved] = useState(false);

  const handleTextChange = (section, key, val) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: val
      }
    }));
  };

  const handleToggle = (section, key) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: !prev[section][key]
      }
    }));
  };

  const triggerSave = () => {
    onSave?.(settings);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const renderAccount = () => {
    const acc = settings.account || {};
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">Personal Information</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Full Name</label>
            <input 
              type="text" 
              value={acc.display_name || ''} 
              onChange={e => handleTextChange('account', 'display_name', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Email Address</label>
            <input 
              type="email" 
              value={acc.email || ''} 
              disabled
              className="border border-neutral-200 p-2.5 rounded-xl bg-neutral-50 text-neutral-400 font-sans text-xs cursor-not-allowed"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Student ID</label>
            <input 
              type="text" 
              value={acc.student_id || ''} 
              onChange={e => handleTextChange('account', 'student_id', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Semester / Term</label>
            <input 
              type="text" 
              value={acc.semester || ''} 
              onChange={e => handleTextChange('account', 'semester', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="col-span-1 sm:col-span-2 flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Institution / University</label>
            <input 
              type="text" 
              value={acc.college || ''} 
              onChange={e => handleTextChange('account', 'college', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
        </div>
      </div>
    );
  };

  const renderVoice = () => {
    const vc = settings.voice || {};
    return (
      <div className="flex flex-col gap-4 font-sans text-xs select-none">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">TTS Engine Voice</h4>
        
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Speech Speed Multiplier ({vc.speech_speed}x)</label>
            <div className="flex items-center gap-4">
              <input 
                type="range" 
                min="0.5" 
                max="2.0" 
                step="0.1" 
                value={vc.speech_speed || 1.0}
                onChange={e => handleTextChange('voice', 'speech_speed', parseFloat(e.target.value))}
                className="w-full h-1.5 bg-neutral-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
            <div className="flex flex-col gap-1.5">
              <label className="font-semibold text-neutral-500 uppercase text-[9px]">Voice Style Persona</label>
              <select 
                value={vc.voice_style || ''} 
                onChange={e => handleTextChange('voice', 'voice_style', e.target.value)}
                className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 font-sans text-xs focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all focus:outline-none"
              >
                <option value="Friendly Mentor">Friendly Mentor</option>
                <option value="Strict Evaluator">Strict Evaluator</option>
                <option value="Fast Code Explainer">Fast Code Explainer</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="font-semibold text-neutral-500 uppercase text-[9px]">Accent Configuration</label>
              <select 
                value={vc.accent || ''} 
                onChange={e => handleTextChange('voice', 'accent', e.target.value)}
                className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 font-sans text-xs focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all focus:outline-none"
              >
                <option value="English (US) - Male">English (US) - Male</option>
                <option value="English (UK) - Female">English (UK) - Female</option>
                <option value="English (IN) - Male">English (IN) - Male</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderLearning = () => {
    const lr = settings.learning || {};
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">Learning Targets</h4>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Preferred Level</label>
            <select 
              value={lr.preferred_difficulty || ''} 
              onChange={e => handleTextChange('learning', 'preferred_difficulty', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 font-sans text-xs focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all focus:outline-none"
            >
              <option value="Beginner">Beginner</option>
              <option value="Medium">Medium</option>
              <option value="Advanced">Advanced</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Placements Target Domain</label>
            <input 
              type="text" 
              value={lr.placement_goal || ''} 
              onChange={e => handleTextChange('learning', 'placement_goal', e.target.value)}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="col-span-1 sm:col-span-2 flex flex-col gap-1.5">
            <label className="font-semibold text-neutral-500 uppercase text-[9px]">Target Target Companies (comma separated)</label>
            <input 
              type="text" 
              value={Array.isArray(lr.preferred_companies) ? lr.preferred_companies.join(', ') : lr.preferred_companies || ''} 
              onChange={e => handleTextChange('learning', 'preferred_companies', e.target.value.split(', '))}
              className="border border-neutral-200 p-2.5 rounded-xl bg-white text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all font-sans text-xs focus:outline-none"
            />
          </div>
        </div>
      </div>
    );
  };

  const renderNotifications = () => {
    const nt = settings.notifications || {};
    return (
      <div className="flex flex-col gap-4 font-sans text-xs select-none">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">System Reminders</h4>
        
        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center bg-white border border-neutral-200 p-4 rounded-xl shadow-sm">
            <div className="flex flex-col">
              <span className="font-sans font-bold text-xs text-neutral-800 leading-tight">Email Updates</span>
              <span className="text-[10px] text-neutral-500 mt-0.5 leading-tight">Receive study stats summary emails weekly</span>
            </div>
            <button 
              onClick={() => handleToggle('notifications', 'email_notifications')}
              className={`w-10 h-6 rounded-full transition-colors flex items-center p-0.5 cursor-pointer ${nt.email_notifications ? 'bg-teal-500' : 'bg-neutral-200'}`}
            >
              <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${nt.email_notifications ? 'translate-x-5' : 'translate-x-0'}`} />
            </button>
          </div>

          <div className="flex justify-between items-center bg-white border border-neutral-200 p-4 rounded-xl shadow-sm">
            <div className="flex flex-col">
              <span className="font-sans font-bold text-xs text-neutral-800 leading-tight">Desktop Alerts</span>
              <span className="text-[10px] text-neutral-500 mt-0.5 leading-tight">Receive streak warning notifications</span>
            </div>
            <button 
              onClick={() => handleToggle('notifications', 'push_notifications')}
              className={`w-10 h-6 rounded-full transition-colors flex items-center p-0.5 cursor-pointer ${nt.push_notifications ? 'bg-teal-500' : 'bg-neutral-200'}`}
            >
              <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${nt.push_notifications ? 'translate-x-5' : 'translate-x-0'}`} />
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderPrivacy = () => {
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">GDPR Data Controls</h4>
        <div className="flex flex-col sm:flex-row gap-3">
          <button className="flex-1 bg-white hover:bg-neutral-50 border border-neutral-200 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all">
            <Download size={14} /> Download Study Log
          </button>
          <button className="flex-1 bg-white hover:bg-neutral-50 border border-neutral-200 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all">
            <ShieldCheck size={14} /> Export Credentials
          </button>
        </div>
      </div>
    );
  };

  const renderConnected = () => {
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-neutral-900 border-b border-neutral-200 pb-2.5 mb-2">Connected Accounts</h4>
        <div className="flex flex-col gap-3">
          {['Google SSO', 'GitHub Developer Link', 'LinkedIn Profile Sync'].map((auth, idx) => (
            <div key={idx} className="flex justify-between items-center bg-white border border-neutral-200 p-4 rounded-xl shadow-sm">
              <span className="font-sans font-semibold text-xs text-neutral-800">{auth}</span>
              <span className="text-[10px] font-semibold text-teal-700 bg-teal-50 border border-teal-100 px-2.5 py-0.5 rounded-full">Linked</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderDanger = () => {
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-red-600 border-b border-red-200 pb-2.5 mb-2">Danger Operations</h4>
        <div className="border border-red-200 bg-red-50/50 p-4 rounded-2xl flex items-start gap-3">
          <AlertTriangle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h5 className="font-sans font-bold text-xs text-red-750 uppercase leading-tight">Irreversible Operations</h5>
            <p className="text-[10.5px] text-neutral-600 mt-1 leading-normal">Deleting your candidate account will permanently purge all local study logs and statistics indexes from PostgreSQL databases.</p>
          </div>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-3 mt-2">
          <button 
            onClick={onLogout}
            className="flex-1 bg-white hover:bg-neutral-50 border border-neutral-200 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all"
          >
            <LogOut size={14} /> Log Out of Account
          </button>
          <button className="flex-1 bg-red-600 text-white hover:bg-red-700 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all">
            <Trash2 size={14} /> Delete Profile Database
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col justify-between bg-white border border-neutral-200 p-6 rounded-2xl shadow-sm min-w-0">
      <div className="flex-1 overflow-y-auto pr-1">
        {activeTab === 'account' && renderAccount()}
        {activeTab === 'voice' && renderVoice()}
        {activeTab === 'learning' && renderLearning()}
        {activeTab === 'notifications' && renderNotifications()}
        {activeTab === 'privacy' && renderPrivacy()}
        {activeTab === 'connected' && renderConnected()}
        {activeTab === 'danger' && renderDanger()}
      </div>

      {activeTab !== 'connected' && activeTab !== 'danger' && (
        <div className="mt-6 border-t border-neutral-100 pt-4 flex justify-end gap-3 flex-shrink-0">
          <button 
            onClick={triggerSave}
            className="bg-teal-500 hover:bg-teal-600 text-white font-sans font-semibold px-6 py-2.5 rounded-xl transition-all cursor-pointer flex items-center gap-2 text-xs shadow-sm"
          >
            <Save size={12} /> {isSaved ? 'Settings Saved!' : 'Save Options'}
          </button>
        </div>
      )}
    </div>
  );
}
