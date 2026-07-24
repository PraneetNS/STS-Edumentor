/**
 * MentorCharacter.jsx
 * 
 * Renders EDI as a friendly 2D bird mascot image.
 * Driven by pipeline states: idle | listening | thinking | speaking.
 * Features a soft bluish gradient background and custom interactive keyframe animations.
 */
import React, { useEffect } from 'react';

export function MentorCharacter({ state = 'idle', analyserNode, onSnapshot }) {
  const onSnapshotCalledRef = React.useRef(false);
  useEffect(() => {
    if (onSnapshot && !onSnapshotCalledRef.current) {
      onSnapshot('/mascot_standing.png');
      onSnapshotCalledRef.current = true;
    }
  }, [onSnapshot]);

  return (
    <div className="mascot-container">
      <style>{`
        .mascot-container {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--bg-secondary);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-2xl);
          overflow: hidden;
          position: relative;
          box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.4);
        }
        
        .mascot-container::before {
          content: '';
          position: absolute;
          inset: 0;
          background-image: 
            linear-gradient(to right, rgba(46, 49, 61, 0.15) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(46, 49, 61, 0.15) 1px, transparent 1px);
          background-size: 20px 20px;
          pointer-events: none;
          z-index: 1;
        }
        
        .mascot-image-wrapper {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          z-index: 2;
        }
        
        .mascot-image {
          max-width: 85%;
          max-height: 85%;
          object-fit: contain;
          mix-blend-mode: multiply;
          filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4));
          transition: all 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        
        /* Interactive States & Micro-animations */
        
        /* LISTENING: soft pulsing green phosphor contour glow */
        .state-listening .mascot-image {
          animation: mascot-listening-pulse 1.8s ease-in-out infinite alternate;
        }
        
        /* THINKING: warm amber filament halo pulse */
        .state-thinking .mascot-image {
          animation: mascot-thinking-pulse 1.4s ease-in-out infinite alternate;
        }
        
        /* SPEAKING: interactive warm filament contour glow */
        .state-speaking .mascot-image {
          animation: mascot-speaking-pulse 1.2s ease-in-out infinite alternate;
        }
        
        @keyframes mascot-listening-pulse {
          0% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 4px rgba(43, 224, 165, 0.2)); }
          100% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 16px rgba(43, 224, 165, 0.5)); }
        }
        
        @keyframes mascot-thinking-pulse {
          0% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 2px rgba(59, 130, 246, 0.2)); }
          100% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.4)); }
        }

        @keyframes mascot-speaking-pulse {
          0% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 4px rgba(59, 130, 246, 0.3)); }
          100% { filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.4)) drop-shadow(0 0 18px rgba(59, 130, 246, 0.6)); }
        }

        @media (prefers-reduced-motion: reduce) {
          .mascot-image, 
          .state-listening .mascot-image, 
          .state-thinking .mascot-image, 
          .state-speaking .mascot-image {
            animation: none !important;
            transition: none !important;
          }
        }
      `}</style>
      <div className={`mascot-image-wrapper state-${state}`}>
        <img 
          src="/mascot_standing.png" 
          alt="Mentor Character" 
          className="mascot-image"
        />
      </div>
    </div>
  );
}
