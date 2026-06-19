/**
 * Waveform — Premium HTML5 Canvas visualizer.
 *
 * Renders overlapping glowing sine waves that react to real-time volume:
 *  - Active Recording (isRecording=true): High-frequency energetic waves.
 *  - Playing Speech (isPlaying=true): Smooth, flowing, wide waves.
 *  - Idle (both false): A slow, breathing, low-amplitude wave.
 *
 * Performance is optimized by running the draw loop within requestAnimationFrame,
 * ensuring 60fps with zero React component re-rendering overhead.
 */
import React, { useEffect, useRef, memo } from 'react';

export const Waveform = memo(function Waveform({
  analyserNode,
  isRecording = false,
  isPlaying = false,
  width = 300,
  height = 80,
}) {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const phaseRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let bufferLength = 0;
    let dataArray = null;

    if (analyserNode) {
      analyserNode.fftSize = 256;
      bufferLength = analyserNode.frequencyBinCount;
      dataArray = new Uint8Array(bufferLength);
    }

    const draw = () => {
      if (!canvas || !ctx) return;
      
      const w = canvas.width;
      const h = canvas.height;
      
      ctx.clearRect(0, 0, w, h);

      // 1. Calculate current volume levels from AnalyserNode
      let volume = 0.02; // baseline idle breathing amplitude
      if (analyserNode && dataArray) {
        analyserNode.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          const val = (dataArray[i] - 128) / 128.0;
          sum += val * val;
        }
        const rms = Math.sqrt(sum / bufferLength);
        volume = Math.max(0.02, rms * 1.5); // amplify volume slightly for visualization
      }

      // If playing but no volume (e.g. silence block), keep a small visual pulse
      if ((isRecording || isPlaying) && volume < 0.05) {
        volume = 0.08;
      }

      // Update wave phase offset
      const speed = isRecording ? 0.15 : isPlaying ? 0.08 : 0.02;
      phaseRef.current += speed;
      const phase = phaseRef.current;

      // Draw 3 overlapping waves with different characteristics for a layered look
      const waves = [
        {
          color: isRecording ? 'rgba(239, 68, 68, 0.25)' : isPlaying ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.1)',
          frequency: 3,
          amplitudeMultiplier: 0.8,
          phaseOffset: 0
        },
        {
          color: isRecording ? 'rgba(244, 63, 94, 0.4)' : isPlaying ? 'rgba(129, 140, 248, 0.4)' : 'rgba(255, 255, 255, 0.15)',
          frequency: 2,
          amplitudeMultiplier: 1.1,
          phaseOffset: Math.PI / 2
        },
        {
          color: isRecording ? 'rgba(251, 113, 133, 0.7)' : isPlaying ? 'rgba(165, 180, 252, 0.7)' : 'rgba(255, 255, 255, 0.25)',
          frequency: 4,
          amplitudeMultiplier: 0.6,
          phaseOffset: Math.PI
        }
      ];

      waves.forEach(wave => {
        ctx.beginPath();
        ctx.strokeStyle = wave.color;
        ctx.lineWidth = wave.amplitudeMultiplier === 0.6 ? 2.5 : 1.5;

        // Add subtle shadow glow to the primary/topmost wave
        if (wave.amplitudeMultiplier === 0.6) {
          ctx.shadowBlur = 10;
          ctx.shadowColor = isRecording ? 'rgba(244, 63, 94, 0.5)' : isPlaying ? 'rgba(129, 140, 248, 0.5)' : 'rgba(255, 255, 255, 0.15)';
        } else {
          ctx.shadowBlur = 0;
        }

        for (let x = 0; x < w; x++) {
          // Normalise x position across canvas width
          const normalizedX = x / w;
          
          // Apply a fade envelope at boundaries so waves taper off nicely on the edges
          const envelope = Math.sin(normalizedX * Math.PI);
          
          // Generate sine wave combining frequency, phase, and volume amplitude
          const angle = (normalizedX * Math.PI * wave.frequency) + phase + wave.phaseOffset;
          const y = (h / 2) + Math.sin(angle) * (h / 2.2) * volume * wave.amplitudeMultiplier * envelope;

          if (x === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
      });

      // Request next frame
      animationRef.current = requestAnimationFrame(draw);
    };

    // Start drawing loop
    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [analyserNode, isRecording, isPlaying]);

  return (
    <div className="waveform-container flex items-center justify-center overflow-hidden">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{ width: `${width}px`, height: `${height}px`, display: 'block' }}
      />
    </div>
  );
});
