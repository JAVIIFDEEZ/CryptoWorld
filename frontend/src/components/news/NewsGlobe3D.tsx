/**
 * components/news/NewsGlobe3D.tsx — Globo terráqueo de noticias geolocalizadas.
 *
 * Esfera con retícula de meridianos/paralelos y un marcador por región del
 * mundo con noticias importantes: tamaño = nº de noticias ponderado por
 * importancia, color = categoría dominante (conflicto, política monetaria,
 * regulación, salida a bolsa, hackeo, adopción, macro). Hover muestra la
 * región; clic selecciona y la página lista sus titulares debajo.
 */

import { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import type { GlobeMarker } from '@/services/newsService'

export const CATEGORY_COLORS: Record<string, string> = {
  conflict: '#ef4444', monetary: '#3b82f6', regulation: '#f59e0b',
  ipo_listing: '#a855f7', hack: '#f43f5e', adoption: '#10b981',
  macro: '#06b6d4', other: '#94a3b8',
}

export const CATEGORY_NAMES: Record<string, string> = {
  conflict: 'Conflicto', monetary: 'Política monetaria', regulation: 'Regulación',
  ipo_listing: 'Salida a bolsa', hack: 'Hackeo', adoption: 'Adopción',
  macro: 'Macro', other: 'Otros',
}

const R = 2.6

/** lat/lon (grados) → coordenadas sobre la esfera. */
function toXYZ(lat: number, lon: number, radius = R): [number, number, number] {
  const la = (lat * Math.PI) / 180
  const lo = (lon * Math.PI) / 180
  return [radius * Math.cos(la) * Math.cos(lo), radius * Math.sin(la), -radius * Math.cos(la) * Math.sin(lo)]
}

function Graticule() {
  const lines = useMemo(() => {
    const group: [number, number, number][][] = []
    for (let lat = -60; lat <= 60; lat += 30) {           // paralelos
      const ring: [number, number, number][] = []
      for (let lon = 0; lon <= 360; lon += 6) ring.push(toXYZ(lat, lon, R))
      group.push(ring)
    }
    for (let lon = 0; lon < 360; lon += 30) {             // meridianos
      const ring: [number, number, number][] = []
      for (let lat = -90; lat <= 90; lat += 6) ring.push(toXYZ(lat, lon, R))
      group.push(ring)
    }
    return group.map((pts) => new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(...p))))
  }, [])
  return (
    <>
      {lines.map((geom, i) => (
        // eslint-disable-next-line react/no-unknown-property
        <line key={i}>
          {/* eslint-disable-next-line react/no-unknown-property */}
          <primitive object={geom} attach="geometry" />
          <lineBasicMaterial color="#1e3a5f" transparent opacity={0.55} />
        </line>
      ))}
    </>
  )
}

function Marker({ m, selected, onSelect }: Readonly<{
  m: GlobeMarker; selected: boolean; onSelect: (region: string) => void
}>) {
  const [hover, setHover] = useState(false)
  const pos = useMemo(() => toXYZ(m.lat, m.lon), [m.lat, m.lon])
  const size = Math.min(0.09 + 0.035 * Math.sqrt(m.importance), 0.3)
  const color = CATEGORY_COLORS[m.top_category] ?? CATEGORY_COLORS.other
  return (
    <group position={pos}>
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); setHover(true) }}
        onPointerOut={() => setHover(false)}
        onClick={(e) => { e.stopPropagation(); onSelect(m.region) }}
      >
        <sphereGeometry args={[size, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hover || selected ? 0.9 : 0.4}
        />
      </mesh>
      {/* Halo del marcador seleccionado */}
      {selected && (
        <mesh>
          <sphereGeometry args={[size * 1.7, 16, 16]} />
          <meshBasicMaterial color={color} transparent opacity={0.18} />
        </mesh>
      )}
      {(hover || selected) && (
        <Html distanceFactor={9} position={[0, size + 0.14, 0]} style={{ pointerEvents: 'none' }}>
          <div className="px-2 py-1 rounded-lg bg-slate-900/95 border border-slate-600 text-[10px] text-white whitespace-nowrap shadow-xl">
            <span className="font-semibold">{m.name}</span>
            <span className="text-slate-400"> · {m.count} noticias</span>
            <span style={{ color }}> · {CATEGORY_NAMES[m.top_category] ?? m.top_category}</span>
          </div>
        </Html>
      )}
    </group>
  )
}

function Scene({ markers, selected, onSelect }: Readonly<{
  markers: GlobeMarker[]; selected: string | null; onSelect: (region: string) => void
}>) {
  const globe = useRef<THREE.Group>(null)
  useFrame((_, delta) => {
    // Rotación lenta que se pausa al seleccionar (para leer el tooltip).
    if (globe.current && !selected) globe.current.rotation.y += delta * 0.06
  })
  return (
    <group ref={globe}>
      <mesh>
        <sphereGeometry args={[R - 0.02, 48, 48]} />
        <meshStandardMaterial color="#0c1b33" roughness={0.9} metalness={0.1} />
      </mesh>
      <Graticule />
      {markers.map((m) => (
        <Marker key={m.region} m={m} selected={selected === m.region} onSelect={onSelect} />
      ))}
    </group>
  )
}

export default function NewsGlobe3D({ markers, selected, onSelect }: Readonly<{
  markers: GlobeMarker[]; selected: string | null; onSelect: (region: string) => void
}>) {
  return (
    <Viz3DFrame camera={[0, 1.6, 6.4]} height={440} autoRotate={false}>
      <Scene markers={markers} selected={selected} onSelect={onSelect} />
    </Viz3DFrame>
  )
}
