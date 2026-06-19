import React from 'react';
import { AvatarFace } from './AvatarFace';
import { getStateClass, getEmotionClass, EMOTIONS } from './AvatarAnimations';

/**
 * EduAvatar — The central visual representation of EDI.
 * 
 * Pure CSS and Framer Motion based (no Three.js) for instant loading, zero latency,
 * and high performance. Driven by the voice pipeline state and an independent emotion layer.
 */
export function EduAvatar({
  isRecording,
  isProcessing,
  isPlaying,
  conversationState,
  analyserNode,
  emotion = EMOTIONS.NORMAL // Allow passing in emotion state
}) {
  const stateClass = getStateClass(conversationState, isRecording, isProcessing, isPlaying);
  const emotionClass = getEmotionClass(emotion);

  return (
    <div className="edi-avatar-wrap">
      <div className={`edi-avatar-container ${stateClass} ${emotionClass}`}>
        {/* Ambient glow behind the avatar */}
        <div className="edi-avatar-glow" style={{
          background: 
            stateClass === 'state-listening' ? 'rgba(124, 58, 237, 0.4)' :
            stateClass === 'state-thinking' ? 'rgba(6, 182, 212, 0.3)' :
            stateClass === 'state-speaking' ? 'rgba(34, 197, 94, 0.3)' :
            'rgba(99, 102, 241, 0.15)'
        }}></div>

        {/* The main avatar head */}
        <div className="edi-head">
          <AvatarFace 
            state={conversationState} 
            isPlaying={isPlaying} 
            analyserNode={analyserNode} 
          />
        </div>

        {/* Ear nodes for tech details */}
        <div className="edi-ear edi-ear--left"></div>
        <div className="edi-ear edi-ear--right"></div>

        {/* Chin detail */}
        <div className="edi-chin"></div>
        
        {/* Particles for THINKING state */}
        {stateClass === 'state-thinking' && (
          <div className="avatar-particles">
            {[...Array(6)].map((_, i) => (
              <div 
                key={i} 
                className="avatar-particle"
                style={{
                  left: `${20 + Math.random() * 60}%`,
                  top: `${Math.random() * 100}%`,
                  animation: `floatUp ${2 + Math.random() * 2}s ease-in infinite`,
                  animationDelay: `${Math.random() * 2}s`
                }}
              ></div>
            ))}
          </div>
        )}

        {/* Rings for LISTENING state */}
        {stateClass === 'state-listening' && (
          <div className="listening-rings">
            {[...Array(3)].map((_, i) => (
              <div 
                key={i} 
                className="listening-ring"
                style={{
                  width: `${140 + i * 40}px`,
                  height: `${140 + i * 40}px`,
                  animationDelay: `${i * 0.6}s`
                }}
              ></div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes floatUp {
          0% { transform: translateY(10px) scale(0.5); opacity: 0; }
          50% { opacity: 0.8; }
          100% { transform: translateY(-40px) scale(1.5); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
