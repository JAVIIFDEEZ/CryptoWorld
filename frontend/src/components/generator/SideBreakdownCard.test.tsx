/**
 * SideBreakdownCard.test.tsx — Que el reparto por lado se pueda leer.
 *
 * El riesgo que cubre esta tarjeta es de lectura, no de cálculo: una estrategia
 * bidireccional con +40 % de retorno puede ser +55 % en largo y −15 % en corto,
 * y sin desglose eso se despliega entero. Los tests comprueban que el lado que
 * pierde se ve como tal y que la explicación del gating llega al usuario.
 */

import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import SideBreakdownCard from './SideBreakdownCard'
import type { SidePerformance } from '@/services/strategyGeneratorService'

function side(over: Partial<SidePerformance> = {}): SidePerformance {
  return {
    n_trades: 24,
    share_of_trades_pct: 60,
    sum_pnl_pct: 55.4,
    mean_pnl_pct: 2.31,
    win_rate_pct: 58.3,
    profit_factor: 1.9,
    standalone_oos_sharpe: 1.12,
    standalone_folds: 4,
    standalone_trades: 26,
    standalone_sharpe: 1.05,
    ...over,
  }
}

describe('SideBreakdownCard', () => {
  it('muestra los dos lados con su aportación', () => {
    render(<SideBreakdownCard sides={{ long: side(), short: side({ n_trades: 16 }) }} />)

    expect(screen.getByText('Largo')).toBeInTheDocument()
    expect(screen.getByText('Corto')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()
    expect(screen.getByText('16')).toBeInTheDocument()
  })

  it('marca el lado que no se sostiene solo', () => {
    render(<SideBreakdownCard sides={{
      long: side({ standalone_oos_sharpe: 1.8 }),
      short: side({ standalone_oos_sharpe: -0.9, sum_pnl_pct: -15.2 }),
    }} />)

    expect(screen.getByText(/✓ aislado 1\.80/)).toBeInTheDocument()
    expect(screen.getByText(/✗ aislado -0\.90/)).toBeInTheDocument()
  })

  it('separa el signo del P&L de cada lado', () => {
    render(<SideBreakdownCard sides={{
      long: side({ sum_pnl_pct: 55.4 }),
      short: side({ sum_pnl_pct: -15.2 }),
    }} />)

    expect(screen.getByText('+55.40%')).toBeInTheDocument()
    expect(screen.getByText('-15.20%')).toBeInTheDocument()
  })

  it('explica en texto por qué el gating bloqueó la estrategia', () => {
    render(<SideBreakdownCard
      sides={{ long: side(), short: side({ standalone_oos_sharpe: -0.9 }) }}
      failures={['el lado corto pierde en aislamiento (Sharpe OOS -0.9, mínimo 0.0)']}
    />)

    expect(screen.getByText(/el lado corto pierde en aislamiento/)).toBeInTheDocument()
  })

  it('no convierte «aún no ha perdido» en un factor de beneficio infinito', () => {
    /* Con 3 operaciones, no haber perdido nunca no significa que no pierda. */
    render(<SideBreakdownCard sides={{
      long: side(),
      short: side({ profit_factor: null, n_trades: 3 }),
    }} />)

    expect(screen.getByText('sin pérdidas')).toBeInTheDocument()
    expect(screen.queryByText('Infinity')).not.toBeInTheDocument()
  })

  it('avisa de que los dos lados comparten una sola posición', () => {
    /* Sin esta nota, un usuario sumaría las operaciones de los dos lados y
       concluiría que faltan. */
    render(<SideBreakdownCard sides={{ long: side(), short: side() }} />)
    expect(screen.getByText(/comparten una sola posición/)).toBeInTheDocument()
  })

  it('usa el umbral que aplicó el gating, no uno fijo', () => {
    const { container } = render(<SideBreakdownCard
      sides={{ long: side({ standalone_oos_sharpe: 0.3 }), short: side({ standalone_oos_sharpe: 0.3 }) }}
      minOosSharpe={0.5}
    />)
    expect(within(container).getAllByText(/✗ aislado 0\.30/)).toHaveLength(2)
  })

  it('marca por separado si el Sharpe de cada lado se distingue de cero', () => {
    /* Agregada, la significancia dice algo que no es de nadie: un Sharpe
       conjunto claramente distinguible de cero puede venir de un lado sólido y
       otro que es puro ruido. */
    render(<SideBreakdownCard sides={{
      long: side({ significance: { significant: true, note: 'sí' } }),
      short: side({ significance: { significant: false, note: 'podría ser ruido' } }),
    }} />)

    expect(screen.getByText('✓ Sharpe distinguible de cero')).toBeInTheDocument()
    expect(screen.getByText('~ podría ser ruido')).toBeInTheDocument()
  })

  it('da la capacidad de cada lado en dinero legible', () => {
    render(<SideBreakdownCard sides={{
      long: side({ capacity: { capacity_usd: 2_400_000 } as SidePerformance['capacity'] }),
      short: side({ capacity: { capacity_usd: 180_000 } as SidePerformance['capacity'] }),
    }} />)

    expect(screen.getByText('capacidad $2.4M')).toBeInTheDocument()
    expect(screen.getByText('capacidad $180K')).toBeInTheDocument()
  })

  it('la capacidad conjunta la marca el lado más estrecho, no la suma', () => {
    /* Los dos lados comparten una sola posición. Sumar sus capacidades
       sobredimensionaría la estrategia justo en el lado donde el impacto de
       mercado haría daño. */
    render(<SideBreakdownCard sides={{
      long: side({ binding_capacity_usd: 180_000 }),
      short: side({ binding_capacity_usd: 180_000 }),
    }} />)

    expect(screen.getByText('$180K')).toBeInTheDocument()
    expect(screen.getByText(/la marca el lado más estrecho, no la suma/)).toBeInTheDocument()
  })

  it('enseña el Sharpe del lado operando solo, que es lo que decide el gating', () => {
    render(<SideBreakdownCard sides={{
      long: side({ standalone_sharpe: 1.44, standalone_trades: 31 }),
      short: side({ standalone_sharpe: -0.2, standalone_trades: 12 }),
    }} />)

    expect(screen.getByText('1.44')).toBeInTheDocument()
    expect(screen.getByText('31')).toBeInTheDocument()
  })
})
