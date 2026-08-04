/**
 * MetaSizingCard.test.tsx — Dirección y tamaño, separados.
 *
 * Lo que esta tarjeta no puede hacer es presentar el overlay como aportando
 * cuando el backend dijo que no, ni ocultar el motivo. «No aporta» es un
 * resultado, no un hueco que rellenar con silencio.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MetaSizingCard from './MetaSizingCard'
import type { MetaSizing } from '@/services/strategyGeneratorService'

const applied: MetaSizing = {
  applied: true,
  meta_model: {
    usable: true,
    n_train: 687,
    n_test: 296,
    test_start_bar: 2028,
    primary_hit_rate: 0.348,
    meta_precision: 0.7,
    edge_over_primary: 0.352,
    signals_taken_pct: 13.5,
  },
  sizing: { mean_size_pct: 4.1, signals_taken: 40, signals_total: 296, floor: 0.5 },
  out_of_sample: {
    from_bar: 2028,
    candles: 972,
    sharpe_flat: 0.051,
    sharpe_conviction: 1.473,
    sharpe_delta: 1.422,
    return_flat_pct: -12.68,
    return_conviction_pct: 4.25,
    max_drawdown_flat_pct: 55.92,
    max_drawdown_conviction_pct: 0.9,
    exposure_flat_pct: 41.56,
    exposure_conviction_pct: 12.96,
    trades_flat: 13,
    trades_conviction: 6,
  },
  improves: true,
  note: 'Dimensionar por convicción mejora aquí el rendimiento ajustado a riesgo.',
}

const noEdge: MetaSizing = {
  applied: false,
  reason: 'no_edge',
  meta_model: { usable: false, primary_hit_rate: 0.52, meta_precision: 0.51 },
  note: 'El meta-modelo no mejora al primario de forma apreciable.',
}

describe('MetaSizingCard', () => {
  it('contrasta el acierto del primario con el del filtro', () => {
    render(<MetaSizingCard meta={applied} />)
    expect(screen.getByText('35%')).toBeInTheDocument()
    expect(screen.getByText('70%')).toBeInTheDocument()
  })

  it('enfrenta el tamaño plano al de convicción en el mismo tramo', () => {
    render(<MetaSizingCard meta={applied} />)
    expect(screen.getByText('0.05')).toBeInTheDocument()
    expect(screen.getByText('1.47')).toBeInTheDocument()
  })

  it('deja ver que el tramo medido es el que el modelo no entrenó', () => {
    render(<MetaSizingCard meta={applied} />)
    expect(screen.getByText(/972 velas desde la 2028/)).toBeInTheDocument()
  })

  it('dice el motivo cuando el overlay no aporta, en vez de callarlo', () => {
    render(<MetaSizingCard meta={noEdge} />)
    expect(screen.getByText(/no supera al primario/i)).toBeInTheDocument()
  })

  it('no inventa una tabla fuera de muestra cuando no hubo comparación', () => {
    render(<MetaSizingCard meta={noEdge} />)
    expect(screen.queryByText(/Efecto fuera de muestra/i)).not.toBeInTheDocument()
  })

  it('no renderiza nada sin datos', () => {
    const { container } = render(<MetaSizingCard />)
    expect(container).toBeEmptyDOMElement()
  })
})
