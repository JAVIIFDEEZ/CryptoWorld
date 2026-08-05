/**
 * ShowcaseTrail.test.tsx — Nada de lo que se vio puede desaparecer sin cuenta.
 *
 * El fallo que esta tarjeta corrige no es de cálculo, es de confianza: una
 * candidata que se vio hacer un +33 % durante la evolución y no vuelve a
 * mencionarse deja al usuario sin poder distinguir «la descartaron por
 * sobreajuste» de «se perdió por el camino». Lo primero es el motor
 * funcionando; lo segundo sería un fallo. Presentar los dos como silencio es lo
 * que hace desconfiar de la herramienta.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ShowcaseTrail from './ShowcaseTrail'
import type { Showcase, ShowcaseRow } from '@/services/strategyGeneratorService'

function row(over: Partial<ShowcaseRow> = {}): ShowcaseRow {
  return {
    hash: 'a1', description: 'ENTRAR si RSI(14) < 30', fitness: 1.51,
    total_return_pct: 33.4, max_drawdown_pct: 12, n_trades: 18,
    disposition: 'in_book', ...over,
  }
}

function showcase(rows: ShowcaseRow[], shown = rows.length): Showcase {
  const counts: Showcase['counts'] = {}
  for (const r of rows) counts[r.disposition] = (counts[r.disposition] ?? 0) + 1
  return { shown, counts, rows, note: '' }
}

describe('ShowcaseTrail', () => {
  it('no se dibuja si no se mostró nada', () => {
    const { container } = render(<ShowcaseTrail showcase={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('encuentra la que hizo un +33 % y dice dónde acabó', () => {
    render(<ShowcaseTrail showcase={showcase([row({ disposition: 'rejected',
      detail: { failed_checks: ['pbo'], near_miss: null } })])} />)

    expect(screen.getByText(/\+33\.4%/)).toBeInTheDocument()
    expect(screen.getByText('descartada')).toBeInTheDocument()
    expect(screen.getByText(/falló: pbo/)).toBeInTheDocument()
  })

  it('separa «no la examinaron» de «la rechazaron»', () => {
    /* Es la distinción que evita leer un silencio como un veredicto: el gating
       tiene presupuesto limitado y se gasta por orden de fitness. */
    render(<ShowcaseTrail showcase={showcase([
      row({ hash: 'x', disposition: 'not_gated' }),
      row({ hash: 'y', disposition: 'rejected', detail: { failed_checks: ['pbo'], near_miss: null } }),
    ])} />)

    expect(screen.getByText('sin examinar')).toBeInTheDocument()
    expect(screen.getByText('descartada')).toBeInTheDocument()
  })

  it('cuenta cada destino en la cabecera', () => {
    render(<ShowcaseTrail showcase={showcase([
      row({ hash: 'a', disposition: 'in_book' }),
      row({ hash: 'b', disposition: 'variant' }),
      row({ hash: 'c', disposition: 'not_gated' }),
      row({ hash: 'd', disposition: 'not_gated' }),
    ])} />)

    expect(screen.getByText('1 en el libro')).toBeInTheDocument()
    expect(screen.getByText('1 variante')).toBeInTheDocument()
    expect(screen.getByText('2 sin examinar')).toBeInTheDocument()
  })

  it('marca el retorno como dentro de muestra', () => {
    /* Sin esto, la tabla se lee como un ranking de rentabilidad y el usuario
       concluye que el motor tiró estrategias buenas. */
    render(<ShowcaseTrail showcase={showcase([row()])} />)

    expect(screen.getByText(/dentro de muestra/)).toBeInTheDocument()
    expect(screen.getByText(/inflado por construcción/)).toBeInTheDocument()
  })

  it('destaca cuando una descartada se quedó rozando el umbral', () => {
    render(<ShowcaseTrail showcase={showcase([row({
      disposition: 'rejected',
      detail: {
        failed_checks: ['mc_p5_positive'],
        near_miss: {
          spec_hash: 'a1', description: '', fitness: 1.5, check: 'mc_p5_positive',
          label: 'percentil 5 del Monte Carlo', observed: -0.02, required: 0,
          gap: 0.02, gap_ratio: 0.0005, note: '',
        },
      },
    })])} />)

    expect(screen.getByText(/a 0\.1%/)).toBeInTheDocument()
  })

  it('avisa de que la tabla es un extracto cuando se mostraron más', () => {
    render(<ShowcaseTrail showcase={showcase([row()], 40)} />)
    expect(screen.getByText(/el recuento de arriba cubre las 40/)).toBeInTheDocument()
  })
})
