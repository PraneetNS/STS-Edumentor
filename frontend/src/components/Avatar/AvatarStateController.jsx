import React, { useRef, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * AvatarStateController — Drives skeletal animations, floating, head-tilting,
 * cursor-tracking, orbiting data rings, and particle systems based on active voice state.
 */
export function AvatarStateController({ children, state, isPlaying, isRecording, isProcessing }) {
  const groupRef = useRef();
  const outerRingsRef = useRef();
  const particlesRef = useRef();

  const { pointer } = useThree();

  useFrame((stateContext) => {
    const time = stateContext.clock.getElapsedTime();
    
    // Resolve active state
    let activeState = 'idle';
    if (state === 'LISTENING' || isRecording) {
      activeState = 'listening';
    } else if (state === 'THINKING' || state === 'TRANSCRIBING' || isProcessing) {
      activeState = 'thinking';
    } else if (state === 'SPEAKING' || isPlaying) {
      activeState = 'speaking';
    }

    if (!groupRef.current) return;

    // ── 1. Breathing & Floating Bobbing Motion ──────────────────────────────
    let bobSpeed = 1.1;
    let bobHeight = 0.04;
    let breathingSpeed = 1.6;
    let breathingScale = 0.012;

    if (activeState === 'thinking') {
      bobSpeed = 2.4;
      bobHeight = 0.015; // Fast, shallow vibration during thinking
      breathingSpeed = 2.2;
    } else if (activeState === 'listening') {
      bobSpeed = 0.7;
      bobHeight = 0.03; // Slow, highly focused sway
      breathingSpeed = 1.2;
    } else if (activeState === 'speaking') {
      bobSpeed = 1.5;
      bobHeight = 0.05; // Slightly bouncy node in sync with speech
      breathingSpeed = 1.8;
    }

    const bobVal = Math.sin(time * bobSpeed) * bobHeight;
    const breathVal = 1.0 + Math.sin(time * breathingSpeed) * breathingScale;

    groupRef.current.position.y = bobVal;
    groupRef.current.scale.setScalar(THREE.MathUtils.lerp(groupRef.current.scale.x, breathVal, 0.15));

    // ── 2. Attentive Head Rotations & Cursor Tracking ────────────────────────
    let targetRotationX = 0;
    let targetRotationY = 0;
    let targetRotationZ = 0;

    if (activeState === 'listening') {
      // Look toward the cursor (interactive user connection)
      targetRotationY = pointer.x * 0.28;
      targetRotationX = -pointer.y * 0.20 + 0.06; // Leans slightly forward (+0.06)
      targetRotationZ = pointer.x * 0.04;
    } else if (activeState === 'thinking') {
      // Looks up and side-to-side periodically as if reflecting
      targetRotationY = Math.sin(time * 0.6) * 0.12;
      targetRotationX = Math.cos(time * 0.5) * 0.06 - 0.05;
    } else if (activeState === 'speaking') {
      // Natural conversational head nods
      targetRotationY = Math.sin(time * 1.3) * 0.07;
      targetRotationX = Math.cos(time * 1.8) * 0.05;
    } else {
      // Idle: very slow breathing yaw/pitch sway
      targetRotationY = Math.sin(time * 0.25) * 0.08;
      targetRotationX = Math.cos(time * 0.18) * 0.04;
    }

    groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, targetRotationX, 0.08);
    groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, targetRotationY, 0.08);
    groupRef.current.rotation.z = THREE.MathUtils.lerp(groupRef.current.rotation.z, targetRotationZ, 0.08);

    // ── 3. Orbital Data Rings Rotation ─────────────────────────────────────
    if (outerRingsRef.current) {
      let ringRotateSpeed = 0.5;
      if (activeState === 'listening') {
        ringRotateSpeed = 1.3;
      } else if (activeState === 'thinking') {
        ringRotateSpeed = 2.4;
      } else if (activeState === 'speaking') {
        ringRotateSpeed = 0.9;
      }

      outerRingsRef.current.rotation.y += ringRotateSpeed * 0.01;
      outerRingsRef.current.rotation.x = Math.sin(time * 0.15) * 0.12;
    }

    // ── 4. Neural Particle Speed and Pulsing ───────────────────────────────
    if (particlesRef.current) {
      let particleRotateSpeed = 0.4;
      let particlePulseSpeed = 1.0;
      if (activeState === 'thinking') {
        particleRotateSpeed = 1.8;
        particlePulseSpeed = 3.5;
      }
      
      particlesRef.current.rotation.y -= particleRotateSpeed * 0.006;
      particlesRef.current.rotation.x = Math.cos(time * 0.25) * 0.08;
      
      const particleScale = 1.0 + Math.sin(time * particlePulseSpeed) * 0.06;
      particlesRef.current.scale.setScalar(particleScale);
    }
  });

  return (
    <group>
      {/* Head / Core Visor */}
      <group ref={groupRef}>
        {children}
      </group>

      {/* Orbiting data rings */}
      <group ref={outerRingsRef}>
        {/* Ring 1 - outer horizontal */}
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.2, 1.215, 64]} />
          <meshBasicMaterial 
            color={
              state === 'LISTENING' || isRecording ? '#a855f7' :
              state === 'THINKING' || state === 'TRANSCRIBING' || isProcessing ? '#0ea5e9' :
              state === 'SPEAKING' || isPlaying ? '#10b981' : '#4f46e5'
            } 
            transparent 
            opacity={0.35} 
          />
        </mesh>

        {/* Ring 2 - inner vertical tilted */}
        <mesh rotation={[Math.PI / 3, Math.PI / 4, 0]}>
          <ringGeometry args={[1.28, 1.29, 64]} />
          <meshBasicMaterial 
            color={
              state === 'LISTENING' || isRecording ? '#d8b4fe' :
              state === 'THINKING' || state === 'TRANSCRIBING' || isProcessing ? '#38bdf8' :
              state === 'SPEAKING' || isPlaying ? '#34d399' : '#818cf8'
            } 
            transparent 
            opacity={0.2} 
          />
        </mesh>
      </group>

      {/* Neural Particle Constellation */}
      <group ref={particlesRef}>
        <PointsState state={state} isProcessing={isProcessing} isRecording={isRecording} isPlaying={isPlaying} />
      </group>
    </group>
  );
}

/**
 * PointsState — Renders a glowing neural point shell that rotates,
 * changes color, and pulses depending on the conversation state.
 */
function PointsState({ state, isProcessing, isRecording, isPlaying }) {
  const pointsRef = useRef();

  const count = 48;
  const [positions, colors] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2.0 * Math.PI;
      const phi = Math.acos(2.0 * v - 1.0);
      
      const r = 1.35 + Math.random() * 0.35;

      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);

      col[i * 3] = 0.0;
      col[i * 3 + 1] = 0.95;
      col[i * 3 + 2] = 1.0;
    }
    return [pos, col];
  }, []);

  useFrame(() => {
    if (!pointsRef.current) return;
    
    const isThinking = state === 'THINKING' || state === 'TRANSCRIBING' || isProcessing;
    const isListening = state === 'LISTENING' || isRecording;
    const isSpeaking = state === 'SPEAKING' || isPlaying;

    const targetSize = isThinking ? 0.09 : 0.055;
    pointsRef.current.material.size = THREE.MathUtils.lerp(pointsRef.current.material.size, targetSize, 0.1);

    let r = 0.3, g = 0.27, b = 0.9; // Default Purpleish Blue
    if (isListening) {
      r = 0.65; g = 0.33; b = 0.96; // Purple
    } else if (isThinking) {
      r = 0.05; g = 0.65; b = 0.91; // Bright sky blue
    } else if (isSpeaking) {
      r = 0.06; g = 0.72; b = 0.5; // Green
    }
    pointsRef.current.material.color.lerp(new THREE.Color(r, g, b), 0.1);
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
        <bufferAttribute
          attach="attributes-color"
          args={[colors, 3]}
        />
      </bufferGeometry>
      <pointsMaterial 
        size={0.055} 
        sizeAttenuation 
        transparent 
        opacity={0.7} 
        vertexColors={false}
        color="#4f46e5"
      />
    </points>
  );
}
