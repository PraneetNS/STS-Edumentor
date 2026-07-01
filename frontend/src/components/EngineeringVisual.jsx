import React, { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';

function IcosahedronMesh() {
  const meshRef = useRef();
  const pointsRef = useRef();

  useFrame((state, delta) => {
    const time = state.clock.getElapsedTime();
    if (meshRef.current) {
      meshRef.current.rotation.x = time * 0.15;
      meshRef.current.rotation.y = time * 0.20;
    }
    if (pointsRef.current) {
      pointsRef.current.rotation.x = time * 0.15;
      pointsRef.current.rotation.y = time * 0.20;
    }
  });

  return (
    <group>
      {/* Wireframe lines */}
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[2.2, 1]} />
        <meshBasicMaterial 
          color="#FF6B00" 
          wireframe 
          transparent 
          opacity={0.7} 
        />
      </mesh>
      
      {/* Dotted Vertex Markers */}
      <points ref={pointsRef}>
        <icosahedronGeometry args={[2.2, 1]} />
        <pointsMaterial 
          color="#FFBC7F" 
          size={0.15} 
          sizeAttenuation 
        />
      </points>
    </group>
  );
}

export function EngineeringVisual() {
  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0, overflow: 'hidden' }}>
      {/* Blueprint grid overlay background */}
      <div 
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(255, 107, 0, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 107, 0, 0.04) 1px, transparent 1px)
          `,
          backgroundSize: '24px 24px',
          backgroundPosition: 'center',
          pointerEvents: 'none',
          zIndex: 1
        }}
      />
      <Canvas camera={{ position: [0, 0, 5] }} style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0, zIndex: 0 }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[5, 5, 5]} intensity={1.5} color="#FF6B00" />
        <IcosahedronMesh />
        <OrbitControls enableZoom={false} enablePan={false} />
      </Canvas>
    </div>
  );
}
