import React from 'react';

export function FloatingShapes({ page }) {
  // Soft, modern color palette matching design tokens
  const blobs = {
    landing: [
      { color: 'rgba(99, 102, 241, 0.25)', top: '15%', left: '10%', size: '300px', delay: '0s', blur: '80px' },
      { color: 'rgba(20, 184, 166, 0.2)', bottom: '15%', right: '15%', size: '350px', delay: '2s', blur: '90px' },
      { color: 'rgba(245, 166, 35, 0.15)', top: '40%', left: '45%', size: '250px', delay: '4s', blur: '70px' },
    ],
    login: [
      { color: 'rgba(59, 130, 246, 0.08)', top: '10%', left: '5%', size: '120px', delay: '0s', blur: '30px' },
      { color: 'rgba(20, 184, 166, 0.06)', bottom: '20%', right: '8%', size: '150px', delay: '1s', blur: '40px' },
    ],
    chat: [], // Keep chat interface clean and distraction-free
    profile: [
      { color: 'rgba(59, 130, 246, 0.05)', top: '20%', left: '10%', size: '200px', delay: '0s', blur: '60px' },
    ]
  };

  const currentBlobs = blobs[page] || [];

  return (
    <div className={`floating-blobs-container page-${page}`}>
      <style>{`
        .floating-blobs-container {
          position: absolute;
          inset: 0;
          overflow: hidden;
          pointer-events: none;
          z-index: 1;
        }

        .floating-blob {
          position: absolute;
          border-radius: 50%;
          mix-blend-mode: multiply;
          will-change: transform;
          animation: blob-float 12s ease-in-out infinite alternate;
        }

        @keyframes blob-float {
          0% {
            transform: translate(0, 0) scale(1) rotate(0deg);
          }
          33% {
            transform: translate(30px, -50px) scale(1.1) rotate(120deg);
          }
          66% {
            transform: translate(-20px, 20px) scale(0.9) rotate(240deg);
          }
          100% {
            transform: translate(0, 0) scale(1) rotate(360deg);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .floating-blob {
            animation: none !important;
          }
        }
      `}</style>

      {currentBlobs.map((blob, idx) => (
        <div
          key={idx}
          className="floating-blob"
          style={{
            top: blob.top,
            bottom: blob.bottom,
            left: blob.left,
            right: blob.right,
            width: blob.size,
            height: blob.size,
            backgroundColor: blob.color,
            filter: `blur(${blob.blur})`,
            animationDelay: blob.delay,
          }}
        />
      ))}
    </div>
  );
}

