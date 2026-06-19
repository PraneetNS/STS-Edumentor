import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * AudioReactiveFace — Renders a futuristic glowing visor/eye interface.
 * Reacts to the WebAudio API analyserNode RMS energy in real-time
 * to simulate mouth movement/visor pulsing during Kokoro speech playback.
 */
export function AudioReactiveFace({ analyserNode, state, isPlaying }) {
  const mouthRef = useRef();
  const eyeLeftRef = useRef();
  const eyeRightRef = useRef();

  const dataArrayRef = useRef(null);

  useFrame(() => {
    let rms = 0;

    // 1. Process real-time WebAudio RMS energy when speaking
    if (isPlaying && analyserNode) {
      if (!dataArrayRef.current) {
        dataArrayRef.current = new Uint8Array(analyserNode.frequencyBinCount);
      }
      
      analyserNode.getByteTimeDomainData(dataArrayRef.current);

      let sum = 0;
      const len = dataArrayRef.current.length;
      for (let i = 0; i < len; i++) {
        const val = (dataArrayRef.current[i] - 128) / 128; // Scale to [-1, 1]
        sum += val * val;
      }
      rms = Math.sqrt(sum / len);
    }

    // 2. Map audio energy to visual scales & neon emissive intensities
    const targetScaleY = isPlaying ? 0.2 + rms * 6.5 : 0.12;
    const targetScaleX = isPlaying ? 1.0 + rms * 1.8 : 1.0;
    const targetIntensity = isPlaying ? 2.5 + rms * 10.0 : 1.5;

    // Shifting color based on conversational state
    let emissiveColor = '#00f3ff'; // Default Cyan
    if (state === 'listening') {
      emissiveColor = '#a855f7'; // Purple
    } else if (state === 'thinking') {
      emissiveColor = '#38bdf8'; // Sky Blue
    } else if (state === 'speaking') {
      emissiveColor = '#10b981'; // Emerald Green
    }

    // Apply scaling and glow with linear interpolation (smoothing)
    if (mouthRef.current) {
      mouthRef.current.scale.y = THREE.MathUtils.lerp(mouthRef.current.scale.y, targetScaleY, 0.25);
      mouthRef.current.scale.x = THREE.MathUtils.lerp(mouthRef.current.scale.x, targetScaleX, 0.25);
      
      if (mouthRef.current.material) {
        mouthRef.current.material.emissive.set(emissiveColor);
        mouthRef.current.material.emissiveIntensity = THREE.MathUtils.lerp(
          mouthRef.current.material.emissiveIntensity,
          targetIntensity,
          0.25
        );
      }
    }

    // 3. Natural Blinking logic (independent of audio)
    const time = Date.now() * 0.001;
    let eyeScaleY = 1.0;
    
    // Cyclic blink check (every 4 seconds, blink duration 150ms)
    const blinkCycle = time % 4.0;
    if (blinkCycle > 3.85) {
      eyeScaleY = 0.05;
    }

    if (eyeLeftRef.current) {
      eyeLeftRef.current.scale.y = THREE.MathUtils.lerp(eyeLeftRef.current.scale.y, eyeScaleY, 0.35);
      if (eyeLeftRef.current.material) {
        eyeLeftRef.current.material.emissive.set(emissiveColor);
      }
    }
    if (eyeRightRef.current) {
      eyeRightRef.current.scale.y = THREE.MathUtils.lerp(eyeRightRef.current.scale.y, eyeScaleY, 0.35);
      if (eyeRightRef.current.material) {
        eyeRightRef.current.material.emissive.set(emissiveColor);
      }
    }
  });

  return (
    <group>
      {/* Left eye */}
      <mesh ref={eyeLeftRef} position={[-0.22, 0.16, 0.42]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial 
          color="#ffffff" 
          emissive="#00f3ff" 
          emissiveIntensity={2.0} 
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>

      {/* Right eye */}
      <mesh ref={eyeRightRef} position={[0.22, 0.16, 0.42]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial 
          color="#ffffff" 
          emissive="#00f3ff" 
          emissiveIntensity={2.0} 
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>

      {/* Visor/mouth element */}
      <mesh ref={mouthRef} position={[0, -0.12, 0.45]}>
        <boxGeometry args={[0.34, 0.08, 0.08]} />
        <meshStandardMaterial 
          color="#ffffff" 
          emissive="#00f3ff" 
          emissiveIntensity={1.5} 
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>
    </group>
  );
}
