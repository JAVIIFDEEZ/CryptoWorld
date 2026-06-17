/**
 * components/landing/HeroParticles3D.tsx — Fondo 3D de la landing.
 *
 * Campo de partículas (dos capas azul/púrpura) que rota lentamente como una
 * galaxia, de adorno tras el contenido del hero. Decorativo y no interactivo;
 * la landing solo lo monta si hay WebGL y el usuario no pidió menos movimiento,
 * y se carga con React.lazy para no penalizar la página pública.
 */

import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function shell(count: number, rMin: number, rMax: number, seed: number): THREE.BufferGeometry {
  const rng = mulberry32(seed)
  const pos = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const r = rMin + rng() * (rMax - rMin)
    const theta = rng() * Math.PI * 2
    const phi = Math.acos(2 * rng() - 1)
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.6 // achatado, tipo galaxia
    pos[i * 3 + 2] = r * Math.cos(phi)
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  return g
}

function mulberry32(a: number) {
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function Cloud({ geom, color, size, speed, opacity }: Readonly<{ geom: THREE.BufferGeometry; color: string; size: number; speed: number; opacity: number }>) {
  const ref = useRef<THREE.Points>(null)
  useFrame((_, d) => { if (ref.current) ref.current.rotation.y += d * speed })
  return (
    <points ref={ref} geometry={geom}>
      <pointsMaterial size={size} color={color} transparent opacity={opacity} sizeAttenuation depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  )
}

export default function HeroParticles3D() {
  const blue = useMemo(() => shell(700, 3, 9, 11), [])
  const purple = useMemo(() => shell(400, 5, 11, 42), [])
  return (
    <Canvas
      camera={{ position: [0, 1.5, 9], fov: 60 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <Cloud geom={blue} color="#3b82f6" size={0.05} speed={0.04} opacity={0.65} />
      <Cloud geom={purple} color="#a855f7" size={0.045} speed={-0.025} opacity={0.45} />
    </Canvas>
  )
}
