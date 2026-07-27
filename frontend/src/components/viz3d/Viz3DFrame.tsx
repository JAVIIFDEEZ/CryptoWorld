/**
 * components/generator/Viz3DFrame.tsx — Envoltorio común de los lienzos 3D.
 *
 * Centraliza el <Canvas> de react-three-fiber con cámara, luces, fondo y
 * controles orbitales coherentes, más un overlay de "arrastra para rotar".
 * Los tres gráficos 3D del generador (universo, paisaje, hélice) lo reutilizan.
 */

import { Suspense, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface Props {
  children: ReactNode
  /** Posición inicial de la cámara. */
  camera?: [number, number, number]
  /** Permitir zoom con la rueda. */
  zoom?: boolean
  /** Rotación automática suave. */
  autoRotate?: boolean
  height?: number
}

export default function Viz3DFrame({
  children,
  camera = [7, 5, 9],
  zoom = true,
  autoRotate = true,
  height = 420,
}: Readonly<Props>) {
  const reduced = useReducedMotion()
  return (
    <div
      className="relative rounded-xl overflow-hidden border border-slate-700/70 bg-[radial-gradient(ellipse_at_center,#0b1426_0%,#070b14_70%)]"
      style={{ height }}
    >
      <Canvas camera={{ position: camera, fov: 50 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.55} />
        <pointLight position={[10, 12, 8]} intensity={1.1} color="#93c5fd" />
        <pointLight position={[-10, -6, -8]} intensity={0.5} color="#a78bfa" />
        <Suspense fallback={null}>{children}</Suspense>
        <OrbitControls
          enablePan={false}
          enableZoom={zoom}
          autoRotate={autoRotate && !reduced}
          autoRotateSpeed={0.6}
          minDistance={5}
          maxDistance={20}
        />
      </Canvas>

      <div className="pointer-events-none absolute bottom-2 left-3 text-[10px] text-slate-500 flex items-center gap-1.5">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M4 9a8 8 0 0114-3m2 9a8 8 0 01-14 3" />
        </svg>
        Arrastra para rotar · rueda para zoom
      </div>
    </div>
  )
}
