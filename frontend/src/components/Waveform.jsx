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

      // FIX 6 — guard: analyserNode may not exist yet when AudioContext hasn't
      // been created (e.g. before any user interaction, or before the first mic
      // capture). Render a flat/idle waveform rather than crash.
      let volume = 0.02; // baseline idle breathing amplitude
      if (analyserNode && dataArray) {
        // Only call getByteTimeDomainData if the analyser is still connected
        // to a live audio graph (avoids InvalidStateError on context close).
        try {
          analyserNode.getByteTimeDomainData(dataArray);
        } catch (_) {
          // analyser was disconnected mid-frame — fall through with baseline volume
        }
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

      // Update wave phase offset (respecting prefers-reduced-motion)
      const hasReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const speed = hasReducedMotion ? 0.003 : (isRecording ? 0.14 : isPlaying ? 0.075 : 0.022);
      phaseRef.current += speed;
      const phase = phaseRef.current;

      // 1. Draw oscilloscope telemetry gridlines
      ctx.strokeStyle = 'rgba(46, 49, 61, 0.15)';
      ctx.lineWidth = 1;
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';

      // Vertical gridlines
      for (let gridX = 20; gridX < w; gridX += 20) {
        ctx.beginPath();
        ctx.moveTo(gridX, 0);
        ctx.lineTo(gridX, h);
        ctx.stroke();
      }

      // Horizontal gridlines
      for (let gridY = 15; gridY < h; gridY += 15) {
        ctx.beginPath();
        ctx.moveTo(0, gridY);
        ctx.lineTo(w, gridY);
        ctx.stroke();
      }

      // 2. Configure glowing traces
      const glowColor = isRecording ? 'rgba(14, 165, 233, 0.85)' : isPlaying ? 'rgba(59, 130, 246, 0.85)' : 'rgba(148, 163, 184, 0.35)';
      const coreColor = isRecording ? '#ffffff' : isPlaying ? '#e0f2fe' : '#94a3b8';
      const shadowGlow = isRecording ? 'rgba(14, 165, 233, 0.9)' : isPlaying ? 'rgba(59, 130, 246, 0.9)' : 'transparent';

      // Draw Thicker Phosphor Glow Trace
      ctx.beginPath();
      ctx.strokeStyle = glowColor;
      ctx.lineWidth = 4.2;
      ctx.shadowBlur = 14;
      ctx.shadowColor = shadowGlow;

      for (let x = 0; x < w; x++) {
        const normalizedX = x / w;
        const envelope = Math.sin(normalizedX * Math.PI);
        const angle = (normalizedX * Math.PI * 4.5) + phase;
        const y = (h / 2) + Math.sin(angle) * (h / 2.3) * volume * envelope;
        
        if (x === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      // Draw Fine Cathode Filament Core Trace
      ctx.beginPath();
      ctx.strokeStyle = coreColor;
      ctx.lineWidth = 1.6;
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';

      for (let x = 0; x < w; x++) {
        const normalizedX = x / w;
        const envelope = Math.sin(normalizedX * Math.PI);
        const angle = (normalizedX * Math.PI * 4.5) + phase;
        const y = (h / 2) + Math.sin(angle) * (h / 2.3) * volume * envelope;
        
        if (x === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

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
