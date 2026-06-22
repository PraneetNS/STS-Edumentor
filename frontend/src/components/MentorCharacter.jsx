/**
 * MentorCharacter.jsx
 * 
 * Renders EDI as a friendly 2D bird mascot image.
 * Driven by pipeline states: idle | listening | thinking | speaking.
 * Features a soft bluish gradient background and custom interactive keyframe animations.
 */
import React, { useEffect } from 'react';

export function MentorCharacter({ state = 'idle', analyserNode, onSnapshot }) {
  // Pass the mascot image URL as the snapshot so logs and lists render correctly
  useEffect(() => {
    if (onSnapshot) {
      onSnapshot('/mascot_standing.png');
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
          background: transparent;
          overflow: visible;
          position: relative;
        }
        
        .mascot-image-wrapper {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
        }
        
        .mascot-image {
          max-width: 95%;
          max-height: 95%;
          object-fit: contain;
          filter: drop-shadow(0 8px 20px rgba(84, 87, 229, 0.16)); /* Contour drop shadow */
          transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        
        /* Interactive States & Micro-animations */
        
        /* IDLE: Fixed and still */
        .state-idle .mascot-image {
          /* Fixed / still state */
        }
        
        /* LISTENING: Fixed with soft pulsing blue glow (no translation/scale movement) */
        .state-listening .mascot-image {
          animation: mascot-glow-pulse 1.8s ease-in-out infinite alternate;
        }
        
        /* THINKING: Fixed and still */
        .state-thinking .mascot-image {
          /* Fixed / still state */
        }
        
        /* SPEAKING: Fixed and still */
        .state-speaking .mascot-image {
          /* Fixed / still state */
        }
        
        @keyframes mascot-glow-pulse {
          0% { filter: drop-shadow(0 8px 20px rgba(84, 87, 229, 0.16)) drop-shadow(0 0 4px rgba(59, 130, 246, 0.2)); }
          100% { filter: drop-shadow(0 8px 20px rgba(84, 87, 229, 0.16)) drop-shadow(0 0 16px rgba(59, 130, 246, 0.6)); }
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
