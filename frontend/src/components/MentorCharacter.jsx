/**
 * MentorCharacter.jsx
 * 
 * Renders EDI as a friendly 3D bird mascot using React Three Fiber.
 * Driven by pipeline states: idle | listening | thinking | speaking.
 * Reacts to pipeline audio energy (analyserNode) for real-time beak sync.
 */
import React, { useRef, useEffect, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { createBirdAvatar } from './BirdAvatar.js';

function BirdCharacterInner({ state, analyserNode, onSnapshot }) {
  const { gl, scene, camera } = useThree();
  const bird = useMemo(() => createBirdAvatar(THREE), []);

  useEffect(() => {
    return () => {
      bird.dispose();
    };
  }, [bird]);

  // Snapshot generation on mount
  const hasCapturedRef = useRef(false);
  useEffect(() => {
    if (onSnapshot && !hasCapturedRef.current) {
      const timer = setTimeout(() => {
        gl.render(scene, camera);
        const dataUrl = gl.domElement.toDataURL('image/png');
        onSnapshot(dataUrl);
        hasCapturedRef.current = true;
      }, 500); // 500ms delay to capture default snapshot
      return () => clearTimeout(timer);
    }
  }, [onSnapshot, gl, scene, camera]);

  // Sync state
  useEffect(() => {
    bird.setState(state);
  }, [bird, state]);

  // Audio reactive RMS tracking array ref
  const dataArrayRef = useRef(null);

  useFrame((threeState, delta) => {
    const time = threeState.clock.getElapsedTime();

    // Calculate real-time RMS amplitude when speaking and analyserNode is present
    let rms = 0;
    if (state === 'speaking' && analyserNode) {
      if (!dataArrayRef.current) {
        dataArrayRef.current = new Uint8Array(analyserNode.frequencyBinCount);
      }
      analyserNode.getByteTimeDomainData(dataArrayRef.current);
      let sum = 0;
      const len = dataArrayRef.current.length;
      for (let i = 0; i < len; i++) {
        const val = (dataArrayRef.current[i] - 128) / 128;
        sum += val * val;
      }
      rms = Math.sqrt(sum / len);
    }
    
    bird.setAmplitude(rms);
    bird.update(time, delta);
  });

  return <primitive object={bird.group} />;
}

export function MentorCharacter({ state = 'idle', analyserNode, onSnapshot }) {
  const canvasRef = useRef(null);

  return (
    <Canvas
      ref={canvasRef}
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      camera={{ fov: 35, position: [0, 0.1, 5] }}
      style={{ width: '100%', height: '100%', display: 'block' }}
    >
      {/* Key light */}
      <pointLight position={[2, 3, 4]} intensity={1.5} color="#ffffff" decay={0} />
      {/* Rim light */}
      <pointLight position={[-3, -1, 2]} intensity={0.6} color="#10B981" decay={0} />
      {/* Ambient lighting */}
      <ambientLight intensity={0.7} color="#606070" />

      <BirdCharacterInner state={state} analyserNode={analyserNode} onSnapshot={onSnapshot} />
    </Canvas>
  );
}
