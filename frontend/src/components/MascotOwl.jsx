import React from 'react';

export function MascotOwl({ className = '', style = {}, state = 'idle', size = '100%' }) {
  return (
    <div className={`edi-mascot-owl ${className} state-${state}`} style={{ ...style, width: size, height: size }}>
      <style>{`
        .edi-mascot-owl {
          display: inline-block;
          position: relative;
          overflow: visible;
        }

        /* Bobbing motion */
        @keyframes owl-bob {
          0%, 100% {
            transform: translateY(0);
          }
          50% {
            transform: translateY(-6px);
          }
        }

        /* Eyes blinking */
        .owl-eye-pupil {
          animation: eye-blink 4s infinite ease-in-out;
          transform-origin: center;
        }
        @keyframes eye-blink {
          0%, 90%, 100% {
            transform: scaleY(1);
          }
          95% {
            transform: scaleY(0.1);
          }
        }

        /* Headset microphone light indicator for states */
        .owl-mic-light {
          fill: var(--neutral-400);
          transition: fill 0.3s;
        }
        .state-listening .owl-mic-light {
          fill: var(--accent-mint);
          animation: mic-pulse 1s infinite alternate;
        }
        .state-thinking .owl-mic-light {
          fill: var(--accent-indigo);
          animation: mic-pulse 1.2s infinite alternate;
        }
        .state-speaking .owl-mic-light {
          fill: var(--accent-amber);
          animation: mic-pulse 0.8s infinite alternate;
        }

        @keyframes mic-pulse {
          0% { opacity: 0.4; }
          100% { opacity: 1; filter: drop-shadow(0 0 4px currentColor); }
        }

        /* Ears shifting slightly on active state */
        .owl-ear {
          transition: transform 0.3s;
        }
        .state-listening .owl-ear-left {
          transform: rotate(-3deg);
        }
        .state-listening .owl-ear-right {
          transform: rotate(3deg);
        }

        /* Reduced Motion check */
        @media (prefers-reduced-motion: reduce) {
          .edi-mascot-owl {
            animation: none !important;
          }
          .owl-eye-pupil {
            animation: none !important;
          }
          .owl-mic-light {
            animation: none !important;
          }
        }
      `}</style>
      <svg
        viewBox="0 0 200 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ width: '100%', height: '100%', overflow: 'visible' }}
      >
        {/* Soft Circular Avatar Background Badge with thin borders */}
        <circle cx="100" cy="100" r="88" fill="var(--neutral-0)" stroke="var(--neutral-200)" strokeWidth="1" />
        
        {/* Inner avatar circle backfill using theme's light blue color */}
        <circle cx="100" cy="100" r="86" fill="var(--blue-50)" />

        {/* Owl Ears */}
        <path className="owl-ear owl-ear-left" d="M55 52 L35 85 L75 75 Z" fill="#74C0FC" stroke="var(--neutral-800)" strokeWidth="2" strokeLinejoin="round" />
        <path className="owl-ear owl-ear-right" d="M145 52 L165 85 L125 75 Z" fill="#74C0FC" stroke="var(--neutral-800)" strokeWidth="2" strokeLinejoin="round" />

        {/* Owl Main Body (Blue #74C0FC) */}
        <ellipse cx="100" cy="115" rx="60" ry="50" fill="#74C0FC" stroke="var(--neutral-800)" strokeWidth="2" />

        {/* Owl Belly patch */}
        <ellipse cx="100" cy="125" rx="42" ry="32" fill="var(--neutral-100)" stroke="var(--neutral-800)" strokeWidth="1.5" />
        
        {/* Cute belly feather marks */}
        <path d="M90 115 Q95 120 100 115" stroke="var(--neutral-800)" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M100 115 Q105 120 110 115" stroke="var(--neutral-800)" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M85 130 Q90 135 95 130" stroke="var(--neutral-800)" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M95 130 Q100 135 105 130" stroke="var(--neutral-800)" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M105 130 Q110 135 115 130" stroke="var(--neutral-800)" strokeWidth="1.5" strokeLinecap="round" />

        {/* Owl Wings (tucked in) */}
        <path d="M40 115 C30 100 35 140 45 145" stroke="var(--neutral-800)" strokeWidth="2" fill="#74C0FC" strokeLinecap="round" />
        <path d="M160 115 C170 100 165 140 155 145" stroke="var(--neutral-800)" strokeWidth="2" fill="#74C0FC" strokeLinecap="round" />

        {/* Headset band */}
        <path d="M50 78 C50 35 150 35 150 78" stroke="var(--neutral-800)" strokeWidth="2" strokeLinecap="round" />

        {/* Owl Eye Sockets (White circles) */}
        <circle cx="75" cy="85" r="24" fill="var(--neutral-0)" stroke="var(--neutral-800)" strokeWidth="2" />
        <circle cx="125" cy="85" r="24" fill="var(--neutral-0)" stroke="var(--neutral-800)" strokeWidth="2" />

        {/* Owl Pupils (Large black circles with light reflection dots) */}
        <g className="owl-eye-pupil">
          <circle cx="77" cy="85" r="12" fill="var(--neutral-800)" />
          <circle cx="73" cy="81" r="4" fill="#FFFFFF" />
          
          <circle cx="123" cy="85" r="12" fill="var(--neutral-800)" />
          <circle cx="119" cy="81" r="4" fill="#FFFFFF" />
        </g>

        {/* Headset ear cushions */}
        <rect x="42" y="70" width="12" height="26" rx="4" fill="var(--accent-coral)" stroke="var(--neutral-800)" strokeWidth="2" />
        <rect x="146" y="70" width="12" height="26" rx="4" fill="var(--accent-coral)" stroke="var(--neutral-800)" strokeWidth="2" />

        {/* Owl Beak (Yellow #FFD60A) */}
        <path d="M100 92 L92 104 L108 104 Z" fill="#FFD60A" stroke="var(--neutral-800)" strokeWidth="2" strokeLinejoin="round" />

        {/* Headset microphone boom arm */}
        <path d="M48 88 L65 106 L82 106" stroke="var(--neutral-800)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="82" cy="106" r="6" className="owl-mic-light" stroke="var(--neutral-800)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}
