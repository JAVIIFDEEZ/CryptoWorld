/**
 * CapacityCard.test.tsx — Capacidad y significancia del campeón.
 *
 * Lo que esta tarjeta no puede hacer es presentar como concluyente un Sharpe
 * cuyo intervalo incluye el cero, ni dar una capacidad cuando la estrategia no
 * sobrevive a su propio impacto de mercado.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CapacityCard from './CapacityCard'
import type { CapacityEstimate, Significance } from '@/services/strategyGeneratorService'

function significance(concluyente: boolean): Significance {
  return {
    confidence_interval: {
      sharpe: 1.8,
      ci_lower: concluyente ? 0.9 : -0.4,
      ci_upper: concluyente ? 2.7 : 4.0,
      confidence: 0.95,
      observations: concluyente ? 1500 : 45,
      excludes_zero: concluyente,
    },
    probabilistic_sharpe: {
      psr: concluyente ? 0.99 : 0.62,
      min_track_record_length: concluyente ? null : 380,
    },
    significant: concluyente,
    note: concluyente
      ? 'El Sharpe es estadísticamente distinguible de cero con este histórico.'
      : 'La magnitud del Sharpe no basta con este histórico: podría ser ruido.',
  }
}

function capacity(usd: number | null): CapacityEstimate {
  return {
    capacity_usd: usd,
    curve: [
      { aum_usd: 1e4, participation_pct: 0.01, impact_bps_per_order: 2, net_sharpe: 1.7, sharpe_retained_pct: 96, feasible: true },
      { aum_usd: 1e6, participation_pct: 1.2, impact_bps_per_order: 22, net_sharpe: 1.1, sharpe_retained_pct: 62, feasible: true },
      { aum_usd: 1e8, participation_pct: 120, impact_bps_per_order: 220, net_sharpe: 0.1, sharpe_retained_pct: 6, feasible: false },
    ],
    note: usd ? 'Capacidad estimada.' : 'Su edge no sobrevive al coste de ejecutarlo.',
  }
}

describe('CapacityCard', () => {
  it('marca como concluyente el Sharpe cuyo intervalo excluye el cero', () => {
    render(<CapacityCard significance={significance(true)} />)
    expect(screen.getByText(/estadísticamente concluyente/i)).toBeInTheDocument()
  })

  it('avisa cuando el intervalo incluye el cero', () => {
    render(<CapacityCard significance={significance(false)} />)
    // Sale en la insignia y de nuevo en la nota del backend.
    expect(screen.getAllByText(/podría ser ruido/i).length).toBeGreaterThan(0)
  })

  it('dice cuántas observaciones harían falta cuando aún no bastan', () => {
    render(<CapacityCard significance={significance(false)} />)
    expect(screen.getByText(/\/ 380/)).toBeInTheDocument()
  })

  it('muestra la capacidad y la degradación del Sharpe por nivel', () => {
    render(<CapacityCard capacity={capacity(1e6)} />)
    // El titular de capacidad y su fila en la tabla comparten el valor.
    expect(screen.getAllByText('1 M$').length).toBeGreaterThan(0)
    expect(screen.getByText('96%')).toBeInTheDocument()
  })

  it('dice "no sobrevive" cuando el edge no aguanta su propio impacto', () => {
    render(<CapacityCard capacity={capacity(null)} />)
    expect(screen.getAllByText(/no sobrevive/i).length).toBeGreaterThan(0)
  })

  it('no renderiza nada sin ninguno de los dos bloques', () => {
    const { container } = render(<CapacityCard />)
    expect(container).toBeEmptyDOMElement()
  })
})
