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
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">Personal Information</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Full Name</label>
            <input
              type="text"
              value={acc.display_name || ''}
              onChange={e => handleTextChange('account', 'display_name', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Email Address</label>
            <input
              type="email"
              value={acc.email || ''}
              disabled
              className="border border-[var(--border-default)]/40 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/30 text-[var(--text-muted)] font-sans text-xs cursor-not-allowed opacity-60"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Student ID</label>
            <input
              type="text"
              value={acc.student_id || ''}
              onChange={e => handleTextChange('account', 'student_id', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Semester / Term</label>
            <input
              type="text"
              value={acc.semester || ''}
              onChange={e => handleTextChange('account', 'semester', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="col-span-1 sm:col-span-2 flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Institution / University</label>
            <input
              type="text"
              value={acc.college || ''}
              onChange={e => handleTextChange('account', 'college', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
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
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">TTS Engine Voice</h4>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">
              Speech Speed Multiplier ({vc.speech_speed || 1.0}x)
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.1"
                value={vc.speech_speed || 1.0}
                onChange={e => handleTextChange('voice', 'speech_speed', parseFloat(e.target.value))}
                className="w-full h-1.5 bg-[var(--bg-tertiary)] rounded-full appearance-none cursor-pointer accent-[var(--accent-indigo)]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
            <div className="flex flex-col gap-1.5">
              <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Voice Style Persona</label>
              <select
                value={vc.voice_style || ''}
                onChange={e => handleTextChange('voice', 'voice_style', e.target.value)}
                className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] font-sans text-xs focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all focus:outline-none"
              >
                <option value="Friendly Mentor">Friendly Mentor</option>
                <option value="Strict Evaluator">Strict Evaluator</option>
                <option value="Fast Code Explainer">Fast Code Explainer</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Voice Selection</label>
              <select
                value={vc.accent || ''}
                onChange={e => handleTextChange('voice', 'accent', e.target.value)}
                className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] font-sans text-xs focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all focus:outline-none"
              >
                <optgroup label="🇺🇸 American — Female">
                  <option value="af_heart">Heart (warm &amp; expressive)</option>
                  <option value="af_bella">Bella (smooth &amp; natural)</option>
                  <option value="af_aoede">Aoede (clear &amp; bright)</option>
                  <option value="af_kore">Kore (calm &amp; balanced)</option>
                  <option value="af_sarah">Sarah (crisp &amp; professional)</option>
                  <option value="af_nova">Nova (energetic &amp; modern)</option>
                  <option value="af_sky">Sky (airy &amp; upbeat)</option>
                  <option value="af_alloy">Alloy (deep &amp; grounded)</option>
                  <option value="af_jessica">Jessica (friendly &amp; warm)</option>
                  <option value="af_nicole">Nicole (soft &amp; gentle)</option>
                  <option value="af_river">River (flowing &amp; relaxed)</option>
                </optgroup>
                <optgroup label="🇺🇸 American — Male">
                  <option value="am_adam">Adam (neutral &amp; clear)</option>
                  <option value="am_echo">Echo (resonant &amp; deep)</option>
                  <option value="am_eric">Eric (confident &amp; steady)</option>
                  <option value="am_fenrir">Fenrir (bold &amp; strong)</option>
                  <option value="am_liam">Liam (casual &amp; approachable)</option>
                  <option value="am_michael">Michael (authoritative)</option>
                  <option value="am_onyx">Onyx (rich &amp; warm)</option>
                  <option value="am_puck">Puck (playful &amp; lively)</option>
                </optgroup>
                <optgroup label="🇬🇧 British — Female">
                  <option value="bf_alice">Alice (elegant &amp; refined)</option>
                  <option value="bf_emma">Emma (clear &amp; polished)</option>
                  <option value="bf_isabella">Isabella (warm &amp; expressive)</option>
                  <option value="bf_lily">Lily (light &amp; melodic)</option>
                </optgroup>
                <optgroup label="🇬🇧 British — Male">
                  <option value="bm_daniel">Daniel (calm &amp; measured)</option>
                  <option value="bm_fable">Fable (storytelling &amp; rich)</option>
                  <option value="bm_george">George (classic &amp; formal)</option>
                  <option value="bm_lewis">Lewis (modern &amp; direct)</option>
                </optgroup>
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
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">Learning Targets</h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Preferred Level</label>
            <select
              value={lr.preferred_difficulty || ''}
              onChange={e => handleTextChange('learning', 'preferred_difficulty', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] font-sans text-xs focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all focus:outline-none"
            >
              <option value="Beginner">Beginner</option>
              <option value="Medium">Medium</option>
              <option value="Advanced">Advanced</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Placements Target Domain</label>
            <input
              type="text"
              value={lr.placement_goal || ''}
              onChange={e => handleTextChange('learning', 'placement_goal', e.target.value)}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
            />
          </div>
          <div className="col-span-1 sm:col-span-2 flex flex-col gap-1.5">
            <label className="font-semibold text-[var(--text-muted)] uppercase text-[9px] tracking-wider">Target Companies (comma separated)</label>
            <input
              type="text"
              value={Array.isArray(lr.preferred_companies) ? lr.preferred_companies.join(', ') : lr.preferred_companies || ''}
              onChange={e => handleTextChange('learning', 'preferred_companies', e.target.value.split(', '))}
              className="border border-[var(--border-default)]/60 p-2.5 rounded-xl bg-[var(--bg-tertiary)]/50 text-[var(--text-primary)] focus:border-[var(--accent-indigo)] focus:ring-2 focus:ring-[var(--accent-indigo-glow)] transition-all font-sans text-xs focus:outline-none"
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
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">System Reminders</h4>

        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center bg-[var(--bg-primary)] border border-[var(--border-default)]/60 p-4 rounded-xl shadow-[0_4px_15px_rgb(0,0,0,0.01)]">
            <div className="flex flex-col">
              <span className="font-sans font-bold text-xs text-[var(--text-primary)] leading-tight">Email Updates</span>
              <span className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-tight">Receive study stats summary emails weekly</span>
            </div>
            <button
              onClick={() => handleToggle('notifications', 'email_notifications')}
              className={`w-10 h-6 rounded-full transition-colors flex items-center p-0.5 cursor-pointer ${nt.email_notifications ? 'bg-[var(--accent-indigo)]' : 'bg-[var(--bg-tertiary)]'}`}
            >
              <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${nt.email_notifications ? 'translate-x-5' : 'translate-x-0'}`} />
            </button>
          </div>

          <div className="flex justify-between items-center bg-[var(--bg-primary)] border border-[var(--border-default)]/60 p-4 rounded-xl shadow-[0_4px_15px_rgb(0,0,0,0.01)]">
            <div className="flex flex-col">
              <span className="font-sans font-bold text-xs text-[var(--text-primary)] leading-tight">Desktop Alerts</span>
              <span className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-tight">Receive streak warning notifications</span>
            </div>
            <button
              onClick={() => handleToggle('notifications', 'push_notifications')}
              className={`w-10 h-6 rounded-full transition-colors flex items-center p-0.5 cursor-pointer ${nt.push_notifications ? 'bg-[var(--accent-indigo)]' : 'bg-[var(--bg-tertiary)]'}`}
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
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">GDPR Data Controls</h4>
        <div className="flex flex-col sm:flex-row gap-3">
          <button className="flex-1 bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)] border border-[var(--border-default)]/60 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all">
            <Download size={14} className="text-indigo-400" /> Download Study Log
          </button>
          <button className="flex-1 bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)] border border-[var(--border-default)]/60 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all">
            <ShieldCheck size={14} className="text-indigo-400" /> Export Credentials
          </button>
        </div>
      </div>
    );
  };

  const renderConnected = () => {
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-[var(--text-primary)] border-b border-[var(--border-default)]/50 pb-2.5 mb-2">Connected Accounts</h4>
        <div className="flex flex-col gap-3">
          {['Google SSO', 'GitHub Developer Link', 'LinkedIn Profile Sync'].map((auth, idx) => (
            <div key={idx} className="flex justify-between items-center bg-[var(--bg-primary)] border border-[var(--border-default)]/60 p-4 rounded-xl shadow-[0_4px_15px_rgb(0,0,0,0.01)]">
              <span className="font-sans font-semibold text-xs text-[var(--text-secondary)]">{auth}</span>
              <span className="text-[10px] font-semibold text-teal-500 bg-teal-500/10 border border-teal-500/20 px-2.5 py-0.5 rounded-full">Linked</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderDanger = () => {
    return (
      <div className="flex flex-col gap-4 font-sans text-xs">
        <h4 className="font-sans font-bold text-sm text-red-500 border-b border-red-500/20 pb-2.5 mb-2">Danger Operations</h4>
        <div className="border border-red-500/20 bg-red-500/5 p-4 rounded-2xl flex items-start gap-3">
          <AlertTriangle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h5 className="font-sans font-bold text-xs text-red-500 uppercase leading-tight">Irreversible Operations</h5>
            <p className="text-[10.5px] text-[var(--text-muted)] mt-1.5 leading-normal">Deleting your candidate account will permanently purge all local study logs and statistics indexes from PostgreSQL databases.</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 mt-2">
          <button
            onClick={onLogout}
            className="flex-1 bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)] border border-[var(--border-default)]/60 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all"
          >
            <LogOut size={14} className="text-[var(--text-secondary)]" /> Log Out of Account
          </button>
          <button className="flex-1 bg-red-500 text-white hover:bg-red-650 p-3 rounded-xl shadow-sm font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all border border-red-600/10">
            <Trash2 size={14} /> Delete Profile Database
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col justify-between bg-[var(--bg-primary)]/80 backdrop-blur-md border border-[var(--border-default)]/60 p-6 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.03)] min-w-0">
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
        <div className="mt-6 border-t border-[var(--border-default)]/40 pt-4 flex justify-end gap-3 flex-shrink-0">
          <button
            onClick={triggerSave}
            className="bg-[var(--accent-indigo)] hover:bg-[var(--accent-indigo-light)] text-white font-sans font-semibold px-6 py-2.5 rounded-xl transition-all cursor-pointer flex items-center gap-2 text-xs shadow-sm hover:shadow-md hover:translate-y-[-1px]"
          >
            <Save size={12} /> {isSaved ? 'Settings Saved!' : 'Save Options'}
          </button>
        </div>
      )}
    </div>
  );
}
