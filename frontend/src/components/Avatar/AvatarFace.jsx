import React, { useRef, useEffect } from 'react';

/**
 * AvatarFace — The expressive face of EDI.
 * 
 * Uses pure CSS and React refs to render the eyes, mouth, and facial features.
 * The mouth animates automatically in the SPEAKING state using the WebAudio API analyserNode.
 */
export function AvatarFace({ state, isPlaying, analyserNode, compact = false }) {
  const mouthRef1 = useRef(null);
  const mouthRef2 = useRef(null);
  const mouthRef3 = useRef(null);
  const reqRef = useRef(null);

  // Audio-reactive mouth animation loop
  useEffect(() => {
    const isSpeaking = state === 'SPEAKING' || isPlaying;
    
    if (!isSpeaking || !analyserNode) {
      if (reqRef.current) cancelAnimationFrame(reqRef.current);
      // Reset mouth to idle state
      const minH = compact ? 2 : 3;
      if (mouthRef1.current) mouthRef1.current.style.height = `${minH}px`;
      if (mouthRef2.current) mouthRef2.current.style.height = `${minH}px`;
      if (mouthRef3.current) mouthRef3.current.style.height = `${minH}px`;
      return;
    }

    const dataArray = new Uint8Array(analyserNode.frequencyBinCount);

    const updateMouth = () => {
      analyserNode.getByteFrequencyData(dataArray);

      // Basic energy calculation
      let sum = 0;
      for (let i = 10; i < 50; i++) {
        sum += dataArray[i];
      }
      const average = sum / 40;
      
      const minH = compact ? 2 : 3;
      const maxH = compact ? 8 : 24;
      const multiplier = compact ? 10 : 30;

      // Map energy to mouth height
      const height = Math.max(minH, Math.min(maxH, (average / 255) * multiplier));

      if (mouthRef1.current) mouthRef1.current.style.height = `${Math.max(minH, height * 0.6)}px`;
      if (mouthRef2.current) mouthRef2.current.style.height = `${height}px`;
      if (mouthRef3.current) mouthRef3.current.style.height = `${Math.max(minH, height * 0.6)}px`;

      reqRef.current = requestAnimationFrame(updateMouth);
    };

    updateMouth();

    return () => {
      if (reqRef.current) cancelAnimationFrame(reqRef.current);
    };
  }, [state, isPlaying, analyserNode]);

  // Occasional random blink
  useEffect(() => {
    const eyes = document.querySelectorAll('.edi-eye');
    let timeoutId;

    const blink = () => {
      eyes.forEach(eye => eye.classList.add('blinking'));
      setTimeout(() => {
        eyes.forEach(eye => eye.classList.remove('blinking'));
      }, 150); // Blink duration

      // Next blink in 3-8 seconds
      timeoutId = setTimeout(blink, 3000 + Math.random() * 5000);
    };

    timeoutId = setTimeout(blink, 2000);

    return () => clearTimeout(timeoutId);
  }, []);

  return (
    <>
      <div className="edi-eyes">
        <div className="edi-eye edi-eye-left">
          <div className="edi-eye-outer">
            <div className="edi-eye-inner"></div>
          </div>
        </div>
        <div className="edi-eye edi-eye-right">
          <div className="edi-eye-outer">
            <div className="edi-eye-inner"></div>
          </div>
        </div>
      </div>
      <div className="edi-mouth mt-4">
        <div ref={mouthRef1} className="edi-mouth-bar"></div>
        <div ref={mouthRef2} className="edi-mouth-bar"></div>
        <div ref={mouthRef3} className="edi-mouth-bar"></div>
      </div>
    </>
  );
}
