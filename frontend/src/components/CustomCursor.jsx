import React, { useEffect, useRef } from 'react';

export function CustomCursor() {
  const dotRef = useRef(null);
  const ringRef = useRef(null);

  // Mouse coords
  const mouse = useRef({ x: 0, y: 0 });
  // Lagged coords for ring
  const ring = useRef({ x: 0, y: 0 });
  const isHovered = useRef(false);

  useEffect(() => {
    const handleMouseMove = (e) => {
      mouse.current.x = e.clientX;
      mouse.current.y = e.clientY;

      const target = e.target;
      if (!target) return;
      
      const isInteractive = target.closest('a, button, input, textarea, select, [role="button"], .quick-chip, .clickable');
      
      if (isInteractive) {
        if (!isHovered.current) {
          isHovered.current = true;
          if (dotRef.current) dotRef.current.classList.add('cursor-hover');
          if (ringRef.current) ringRef.current.classList.add('cursor-hover');
        }
      } else {
        if (isHovered.current) {
          isHovered.current = false;
          if (dotRef.current) dotRef.current.classList.remove('cursor-hover');
          if (ringRef.current) ringRef.current.classList.remove('cursor-hover');
        }
      }
    };

    window.addEventListener('mousemove', handleMouseMove);

    const ease = 0.15;
    let animationFrameId;

    const updateCursor = () => {
      if (dotRef.current) {
        dotRef.current.style.transform = `translate3d(${mouse.current.x}px, ${mouse.current.y}px, 0)`;
      }

      ring.current.x += (mouse.current.x - ring.current.x) * ease;
      ring.current.y += (mouse.current.y - ring.current.y) * ease;

      if (ringRef.current) {
        ringRef.current.style.transform = `translate3d(${ring.current.x}px, ${ring.current.y}px, 0)`;
      }

      animationFrameId = requestAnimationFrame(updateCursor);
    };

    updateCursor();

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <>
      <div className="custom-cursor-container">
        <style>{`
          .custom-cursor-container {
            pointer-events: none;
            position: fixed;
            inset: 0;
            z-index: 99999;
          }
          
          /* Only show custom cursor if device has mouse/fine pointer */
          @media (pointer: fine) {
            .cursor-dot {
              position: fixed;
              top: -6px;
              left: -6px;
              width: 12px;
              height: 12px;
              background-color: var(--coral);
              border-radius: 50%;
              pointer-events: none;
              z-index: 100000;
              transition: background-color 0.2s, width 0.2s, height 0.2s, top 0.2s, left 0.2s;
              will-change: transform;
            }
            
            .cursor-ring {
              position: fixed;
              top: -20px;
              left: -20px;
              width: 40px;
              height: 40px;
              border: 3px solid var(--black);
              border-radius: 50%;
              pointer-events: none;
              z-index: 99999;
              transition: width 0.2s, height 0.2s, top 0.2s, left 0.2s, background-color 0.2s;
              will-change: transform;
            }
            
            .cursor-dot.cursor-hover {
              width: 16px;
              height: 16px;
              top: -8px;
              left: -8px;
              background-color: var(--yellow);
              border: 2px solid var(--black);
            }
            
            .cursor-ring.cursor-hover {
              width: 50px;
              height: 50px;
              top: -25px;
              left: -25px;
              background-color: rgba(196, 181, 255, 0.3);
            }
          }
          
          @media (pointer: coarse) {
            .cursor-dot, .cursor-ring {
              display: none !important;
            }
          }
        `}</style>
        <div ref={dotRef} className="cursor-dot" />
        <div ref={ringRef} className="cursor-ring" />
      </div>
    </>
  );
}
