/**
 * Generator2DFallback.test.tsx — Fallback 2D del ADN de la estrategia.
 *
 * Dna2D es DOM puro (sin canvas ni recharts), así que verificamos que pinta las
 * condiciones de entrada y salida de un spec con sus etiquetas legibles.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Dna2D } from './Generator2DFallback'
import type { StrategySpec } from '@/services/strategyGeneratorService'

const SPEC: StrategySpec = {
  entry: {
    combine: 'AND',
    conditions: [
      { type: 'threshold', indicator: 'RSI', params: { window: 14 }, op: 'lt', threshold: 30 },
      { type: 'cross', op: 'cross_above', a: { indicator: 'EMA', params: { window: 12 } }, b: { indicator: 'SMA', params: { window: 26 } } },
    ],
  },
  exit: {
    combine: 'OR',
    conditions: [
      { type: 'threshold', indicator: 'RSI', params: { window: 14 }, op: 'gt', threshold: 70 },
    ],
  },
}

describe('Dna2D', () => {
  it('renders entry and exit blocks with readable condition labels', () => {
    render(<Dna2D spec={SPEC} />)
    expect(screen.getByText('Entrada')).toBeInTheDocument()
    expect(screen.getByText('Salida')).toBeInTheDocument()
    expect(screen.getByText('RSI < 30')).toBeInTheDocument()
    expect(screen.getByText('EMA ↗ SMA')).toBeInTheDocument()
    expect(screen.getByText('RSI > 70')).toBeInTheDocument()
  })

  it('shows an empty state when there is no winning strategy', () => {
    render(<Dna2D spec={null} />)
    expect(screen.getByText(/Sin estrategia ganadora/i)).toBeInTheDocument()
  })
})
