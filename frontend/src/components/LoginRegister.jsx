import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { authStore } from '../stores/authStore';
import { EngineeringVisual } from './EngineeringVisual';
import { Shield, Mail, Lock, User, AlertTriangle, CheckCircle } from 'lucide-react';

export function LoginRegister() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const login = authStore.getState().login;
  const register = authStore.getState().register;

  // Check URL parameters for email verification or callbacks
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('verified') === 'true') {
      setSuccess('Email address verified successfully. You can now login.');
      // Clean query parameter
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setIsLoading(true);

    try {
      if (isLogin) {
        await login(email, password);
      } else {
        const data = await register(email, password, displayName);
        setSuccess(data.message || 'Registration successful. Check email to verify.');
        // Clear fields
        setEmail('');
        setPassword('');
        setDisplayName('');
        setIsLogin(true);
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
    window.location.href = `${API_BASE}/auth/google`;
  };

  return (
    <div className="relative w-full h-screen overflow-hidden bg-[#0A0B0E] flex items-center justify-center font-mono">
      {/* ZONE 0: 3D Canvas visible behind the form */}
      <EngineeringVisual />

      {/* Ambient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-[#0A0B0E] via-transparent to-transparent opacity-80 pointer-events-none z-[1]" />

      {/* Auth centered card */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className="w-full max-w-[420px] mx-4 border border-slate-800 bg-[#0F1117]/85 backdrop-blur-xl p-8 rounded shadow-2xl relative z-10"
      >
        {/* Decorative blueprint corners */}
        <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-orange-500" />
        <div className="absolute top-0 right-0 w-3 h-3 border-t-2 border-r-2 border-orange-500" />
        <div className="absolute bottom-0 left-0 w-3 h-3 border-b-2 border-l-2 border-orange-500" />
        <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-orange-500" />

        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center p-2.5 bg-orange-950/20 border border-orange-500/20 rounded text-orange-500 mb-3">
            <Shield size={24} />
          </div>
          <h2 className="text-white font-bold text-base uppercase tracking-wider">EDUMENTOR GATEWAY</h2>
          <p className="text-[10px] text-slate-500 mt-1">SECURE LOGICAL AUTHENTICATION PIPELINE</p>
        </div>

        {/* Feedback alerts */}
        <AnimatePresence mode="wait">
          {error && (
            <motion.div 
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="bg-rose-950/25 border border-rose-500/30 text-rose-400 p-3 rounded text-[11px] mb-4 flex items-start gap-2 overflow-hidden"
            >
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div>{error}</div>
            </motion.div>
          )}

          {success && (
            <motion.div 
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="bg-emerald-950/25 border border-emerald-500/30 text-emerald-400 p-3 rounded text-[11px] mb-4 flex items-start gap-2 overflow-hidden"
            >
              <CheckCircle size={14} className="mt-0.5 shrink-0" />
              <div>{success}</div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Input Forms */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 text-xs">
          
          {!isLogin && (
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] text-slate-400 uppercase tracking-wide">DISPLAY NAME</label>
              <div className="relative">
                <User size={14} className="absolute left-3 top-3 text-slate-500" />
                <input
                  type="text"
                  required
                  placeholder="Enter name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full bg-[#07090C] border border-slate-800 focus:border-orange-500 text-white pl-9 pr-3 py-2.5 rounded focus:outline-none transition-colors"
                />
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-400 uppercase tracking-wide">EMAIL ADDRESS</label>
            <div className="relative">
              <Mail size={14} className="absolute left-3 top-3 text-slate-500" />
              <input
                type="email"
                required
                placeholder="student@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-[#07090C] border border-slate-800 focus:border-orange-500 text-white pl-9 pr-3 py-2.5 rounded focus:outline-none transition-colors"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-400 uppercase tracking-wide">PASSWORD</label>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-3 text-slate-500" />
              <input
                type="password"
                required
                placeholder="******"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-[#07090C] border border-slate-800 focus:border-orange-500 text-white pl-9 pr-3 py-2.5 rounded focus:outline-none transition-colors"
              />
            </div>
          </div>

          {/* Action buttons */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded text-xs uppercase tracking-wider transition-colors disabled:opacity-50 mt-2 cursor-pointer"
          >
            {isLoading ? 'EXECUTING PIPELINE...' : isLogin ? 'INITIATE SESSION' : 'REGISTER STUDENT'}
          </button>

          <div className="flex items-center my-2 select-none">
            <div className="grow h-px bg-slate-800" />
            <span className="px-3 text-[9px] text-slate-500 uppercase">OR CONNECT WITH</span>
            <div className="grow h-px bg-slate-800" />
          </div>

          {/* Google SSO */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            className="w-full bg-[#13151D] hover:bg-[#1C1F2B] border border-slate-800 text-slate-300 font-bold py-2.5 rounded flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            <svg width="14" height="14" viewBox="0 0 24 24">
              <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" strokeWidth="0" />
              <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            <span className="text-xs uppercase tracking-wide">Google SSO</span>
          </button>
        </form>

        {/* View Toggle */}
        <div className="text-center mt-6">
          <button 
            type="button" 
            onClick={() => {
              setIsLogin(!isLogin);
              setError('');
              setSuccess('');
            }}
            className="text-[10px] text-slate-400 hover:text-orange-500 underline transition-colors cursor-pointer"
          >
            {isLogin ? "NEW STUDENT? INITIALIZE REGISTRATION" : "EXISTING STUDENT? ROUTE TO GATEWAY"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
