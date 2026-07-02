import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { authStore } from '../stores/authStore';
import { Shield, Mail, Lock, User, AlertTriangle, CheckCircle } from 'lucide-react';
import { MascotOwl } from './MascotOwl';
import { FloatingShapes } from './FloatingShapes';
import { CustomCursor } from './CustomCursor';

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('verified') === 'true') {
      setSuccess('Email address verified successfully. You can now login.');
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
    <div className="w-full h-screen overflow-hidden flex flex-col md:grid md:grid-cols-2 relative select-none bg-[var(--neutral-100)]">
      {/* Ambient background */}
      <div className="ambient-bg" aria-hidden="true" />

      {/* LEFT COLUMN: Mascot & Branding Showcase (Premium Deep Blue Mesh Block) */}
      <div className="hidden md:flex bg-gradient-to-br from-[#0d1b3e] via-[#1a2d5a] to-[#0a1628] flex-col items-center justify-center p-6 lg:p-12 relative overflow-hidden">
        {/* Floating shapes behind mascot */}
        <FloatingShapes page="login" />

        {/* Subtle radial glow behind the bird */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div style={{
            width: '340px', height: '340px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(99,132,255,0.18) 0%, rgba(99,132,255,0.06) 55%, transparent 75%)',
            filter: 'blur(8px)',
          }} />
        </div>

        {/* Decorative arc rings */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div style={{ width: '300px', height: '300px', borderRadius: '50%', border: '1px solid rgba(255,255,255,0.06)' }} />
        </div>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div style={{ width: '420px', height: '420px', borderRadius: '50%', border: '1px solid rgba(255,255,255,0.04)' }} />
        </div>

        <div className="relative z-10 flex flex-col items-center max-w-sm text-center">
          {/* Bird mascot with shade overlay */}
          <div className="relative w-52 h-52 mb-8 flex items-center justify-center">
            {/* Soft shadow platform under the bird */}
            <div style={{
              position: 'absolute', bottom: '-8px', left: '50%', transform: 'translateX(-50%)',
              width: '140px', height: '24px',
              background: 'radial-gradient(ellipse, rgba(0,0,0,0.35) 0%, transparent 70%)',
              borderRadius: '50%',
              filter: 'blur(6px)',
            }} />
            {/* Bird image */}
            <img
              src="/mascot.png"
              alt="EduMentor Mascot — Edi the Owl"
              className="w-full h-full object-contain relative z-10"
              style={{
                filter: 'drop-shadow(0 12px 32px rgba(59,130,246,0.25)) drop-shadow(0 4px 12px rgba(0,0,0,0.4))',
              }}
            />
            {/* Cool-toned shade overlay (blue tint at bottom of bird) */}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0, height: '40%',
              background: 'linear-gradient(to top, rgba(13,27,62,0.45) 0%, transparent 100%)',
              borderRadius: '0 0 50% 50%',
              zIndex: 11,
              pointerEvents: 'none',
            }} />
          </div>

          {/* Speech Bubble */}
          <div className="bg-white/10 backdrop-blur-sm border border-white/20 p-4 rounded-2xl shadow-lg mb-6 relative">
            <div className="absolute bottom-[-6px] left-[50%] translate-x-[-50%] w-3 h-3 bg-white/10 border-b border-r border-white/20 rotate-45" />
            <p className="font-sans font-semibold text-xs text-white/90">
              "Hey there! I am EDI, your AI Engineering Voice Tutor."
            </p>
          </div>

          <h1 className="font-sans font-extrabold text-3xl tracking-tight text-white mb-4">
            Master Your Concepts
          </h1>
          <p className="font-sans text-sm text-blue-200/80 leading-relaxed">
            Real-time interactive voice guidance for CS, Mechanical, Electrical, Civil and Aerospace coursework. 100% private.
          </p>
        </div>

        {/* Small sticker decoration */}
        <div className="absolute bottom-6 left-6 bg-white/10 text-white/80 border border-white/20 font-sans font-medium text-[10px] px-3.5 py-1.5 rounded-full shadow-sm">
          EDU-GATEWAY v4.0
        </div>

        {/* Round logo top-left */}
        <div className="absolute top-6 left-6 flex items-center gap-2">
          <div style={{
            width: '36px', height: '36px', borderRadius: '50%',
            overflow: 'hidden', border: '2px solid rgba(255,255,255,0.2)',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}>
            <img src="/mascot.png" alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
          <span className="font-sans font-bold text-white/90 text-sm tracking-tight">EduMentor</span>
        </div>
      </div>

      {/* RIGHT COLUMN: Authentication Form (White/Yellow Accent Card) */}
      <div className="flex-1 flex items-center justify-center p-6 bg-transparent relative overflow-y-auto">
        {/* Floating shapes on mobile background */}
        <div className="md:hidden">
          <FloatingShapes page="login" />
        </div>

        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-[400px] bg-white p-6 sm:p-8 rounded-2xl shadow-xl border border-neutral-100 relative z-10"
        >
          {/* Header */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-50 text-blue-600 rounded-2xl mb-3 shadow-sm">
              <Shield size={22} />
            </div>
            <h2 className="font-sans font-extrabold text-xl tracking-tight text-neutral-900">
              EDUMENTOR SIGN-IN
            </h2>
            <p className="font-sans text-xs text-neutral-500 mt-1">
              Secure Logical Authentication Pipeline
            </p>
          </div>

          {/* Alerts */}
          <AnimatePresence mode="wait">
            {error && (
              <motion.div 
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="bg-red-50 border border-red-100 text-red-700 p-3.5 rounded-xl text-xs font-sans mb-4 flex items-start gap-2 shadow-sm"
              >
                <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                <div>{error}</div>
              </motion.div>
            )}

            {success && (
              <motion.div 
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="bg-teal-50 border border-teal-100 text-teal-700 p-3.5 rounded-xl text-xs font-sans mb-4 flex items-start gap-2 shadow-sm"
              >
                <CheckCircle size={15} className="shrink-0 mt-0.5" />
                <div>{success}</div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {!isLogin && (
              <div className="flex flex-col gap-1.5">
                <label className="font-sans font-semibold text-xs text-neutral-700">Display Name</label>
                <div className="relative">
                  <User size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <input
                    type="text"
                    required
                    placeholder="Praneet N.S."
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="w-full h-12 bg-white border border-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-black pl-11 pr-4 rounded-xl font-sans text-sm focus:outline-none transition-all placeholder-neutral-400"
                  />
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="font-sans font-semibold text-xs text-neutral-700">Email Address</label>
              <div className="relative">
                <Mail size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
                <input
                  type="email"
                  required
                  placeholder="student@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-12 bg-white border border-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-black pl-11 pr-4 rounded-xl font-sans text-sm focus:outline-none transition-all placeholder-neutral-400"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-sans font-semibold text-xs text-neutral-700">Security Phrase (Password)</label>
              <div className="relative">
                <Lock size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-12 bg-white border border-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-black pl-11 pr-4 rounded-xl font-sans text-sm focus:outline-none transition-all placeholder-neutral-400"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full clay-btn-primary h-12 flex items-center justify-center text-sm font-semibold tracking-wider disabled:opacity-50 mt-2 cursor-pointer"
            >
              {isLoading ? 'Executing Request...' : isLogin ? 'INITIATE GATEWAY SESSION' : 'REGISTER STUDENT'}
            </button>

            {/* Divider */}
            <div className="flex items-center my-1 select-none">
              <div className="grow h-[1px] bg-neutral-200" />
              <span className="px-3 font-sans font-medium text-[10px] text-neutral-400 uppercase">OR CONNECT WITH</span>
              <div className="grow h-[1px] bg-neutral-200" />
            </div>

            {/* Google SSO Button */}
            <button
              type="button"
              onClick={handleGoogleLogin}
              className="w-full h-12 border border-neutral-200 rounded-full flex items-center justify-center gap-2 hover:bg-neutral-50 transition-all font-sans font-semibold text-neutral-700 bg-white shadow-sm cursor-pointer"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" className="shrink-0">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" strokeWidth="0" />
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              <span className="text-xs uppercase tracking-wide">Google SSO</span>
            </button>
          </form>

          {/* Toggle Link */}
          <div className="text-center mt-6">
            <button 
              type="button" 
              onClick={() => {
                setIsLogin(!isLogin);
                setError('');
                setSuccess('');
              }}
              className="font-sans text-xs text-blue-600 hover:text-blue-700 hover:underline transition-colors cursor-pointer font-semibold"
            >
              {isLogin ? "New Student? Setup Credentials" : "Existing Student? Return to Gateway"}
            </button>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
