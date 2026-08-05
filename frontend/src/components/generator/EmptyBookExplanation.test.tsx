/**
 * EmptyBookExplanation.test.tsx — Que el libro vacío no mienta sobre su causa.
 *
 * Tres causas, tres acciones opuestas: faltan datos (repetir con más
 * histórico), el mercado no ofrece edge (probar otro activo o marco), un lado
 * sangraba (repetir en una sola dirección). Confundirlas no es un matiz de
 * redacción — manda al usuario en la dirección equivocada, y en el caso del
 * lado le hace descartar un edge que sí existía.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EmptyBookExplanation from './EmptyBookExplanation'
import type { GenerationPower, GenerationReport } from '@/services/strategyGeneratorService'

function power(over: Partial<GenerationPower> = {}): GenerationPower {
  return {
    candles: 2400, interval: '1h', span_days: 100, evolution_candles: 1920,
    wf_splits: 4, bars_per_fold: 384, days_per_fold: 16,
    trades_observed: 48, trades_per_fold: 12,
    reliability: 'adequate', limits: [],
    ...over,
  } as GenerationPower
}

function report(failed: string[][]): GenerationReport {
  return {
    rejected: failed.map((failed_checks, i) => ({
      spec_hash: `h${i}`, description: 'x', fitness: 1, passed_gating: false,
      pbo: null, wf_efficiency: null, oos_sharpe: null, sharpe: null,
      n_trades: null, total_return_pct: null, max_drawdown_pct: null,
      failed_checks,
    })),
  } as unknown as GenerationReport
}

describe('EmptyBookExplanation', () => {
  it('no culpa al mercado cuando lo que faltaban eran datos', () => {
    render(<EmptyBookExplanation power={power({ reliability: 'insufficient' })} />)

    expect(screen.getByText(/no por el mercado: por falta de datos/)).toBeInTheDocument()
    expect(screen.getByText(/marco mayor \(4h o 1d\)/)).toBeInTheDocument()
  })

  it('sí habla del mercado cuando había potencia para juzgarlo', () => {
    render(<EmptyBookExplanation power={power()} report={report([['pbo', 'mc_p5_positive']])} />)

    expect(screen.getByText(/Ninguna estrategia superó el gating/)).toBeInTheDocument()
    expect(screen.getByText(/el resultado sí habla del mercado/)).toBeInTheDocument()
  })

  it('distingue el caso en que había edge pero solo en un lado', () => {
    render(<EmptyBookExplanation
      power={power()}
      report={report([['sides_stand_alone'], ['sides_stand_alone'], ['sides_stand_alone']])}
    />)

    expect(screen.getByText('Había edge, pero solo en un lado.')).toBeInTheDocument()
    expect(screen.getByText(/3 de 3 candidatas pasaron TODO el gating/)).toBeInTheDocument()
    expect(screen.getByText(/Repite la búsqueda en una sola dirección/)).toBeInTheDocument()
  })

  it('no atribuye al lado lo que también falló por otras cosas', () => {
    /* Una candidata que además falla el PBO no demuestra nada sobre el lado:
       habría caído igual. Contarla inflaría la explicación. */
    render(<EmptyBookExplanation
      power={power()}
      report={report([['sides_stand_alone', 'pbo'], ['pbo'], ['min_trades']])}
    />)

    expect(screen.queryByText('Había edge, pero solo en un lado.')).not.toBeInTheDocument()
    expect(screen.getByText(/Ninguna estrategia superó el gating/)).toBeInTheDocument()
  })

  it('la falta de datos manda sobre el motivo del lado', () => {
    /* Con el histórico corto, ni el control por lado significa nada: se está
       midiendo ruido en los dos lados. Lo primero que hay que arreglar es el
       histórico. */
    render(<EmptyBookExplanation
      power={power({ reliability: 'insufficient' })}
      report={report([['sides_stand_alone'], ['sides_stand_alone']])}
    />)

    expect(screen.getByText(/por falta de datos/)).toBeInTheDocument()
    expect(screen.queryByText('Había edge, pero solo en un lado.')).not.toBeInTheDocument()
  })

  it('enseña las operaciones por tramo, que es lo que decide si el veredicto vale', () => {
    render(<EmptyBookExplanation power={power({ trades_per_fold: 3 })} />)

    expect(screen.getByText('Por tramo')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('se sostiene sin informe: la tarjeta es la misma con o sin rechazadas', () => {
    render(<EmptyBookExplanation power={power()} />)
    expect(screen.getByText(/Ninguna estrategia superó el gating/)).toBeInTheDocument()
  })
})
