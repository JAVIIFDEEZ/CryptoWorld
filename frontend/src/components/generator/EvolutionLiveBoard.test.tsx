/**
 * EvolutionLiveBoard.test.tsx — Que el tablero en vivo se pueda leer y no engañe.
 *
 * Dos problemas distintos, los dos visibles en cuanto arranca una ejecución:
 *
 *   1. **La escala.** En la generación 0 la población está llena de genomas
 *      degenerados que el fitness penaliza a −65, mientras que todo lo
 *      interesante vive entre 0 y 2. Con un dominio ingenuo, ese único punto se
 *      lleva el 97 % del alto y las dos series quedan pegadas al borde superior
 *      como líneas planas.
 *   2. **El significado de los números.** Los retornos de las tarjetas son
 *      dentro de muestra. Enseñar un +107 % en verde sin decirlo, y después un
 *      libro vacío, da a entender que el motor encontró algo bueno y lo tiró.
 *      Es al revés: enseñó un número que no significa nada y luego se negó a
 *      avalarlo.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EvolutionLiveBoard, { domainOf } from './EvolutionLiveBoard'
import type { EvolutionProgress, GenerationHistoryPoint } from '@/services/strategyGeneratorService'

function hist(pairs: [number, number][]): GenerationHistoryPoint[] {
  return pairs.map(([best, mean], i) => ({ generation: i, best, mean, diversity: 40 }))
}

describe('domainOf', () => {
  it('no deja que un solo punto catastrófico fije el suelo', () => {
    /* El caso real: media −65.94 en la generación 0, todo lo demás entre 1 y 2. */
    const d = domainOf(hist([[1.5, -65.94], [1.7, 0.9], [1.98, 1.4]]))

    expect(d.clipped).toBe(true)
    expect(d.trueLo).toBe(-65.94)
    // El suelo sube muchísimo respecto al mínimo real…
    expect(d.lo).toBeGreaterThan(-1)
    // …pero sin comerse las medias normales, que son información útil.
    expect(d.lo).toBeLessThan(0.9)
  })

  it('no recorta una media simplemente rezagada', () => {
    /* Una media por debajo del mejor es lo normal —la población aún no lo ha
       alcanzado— y es información útil. Solo el arranque catastrófico se
       recorta; confundir las dos cosas perdería la mitad del gráfico. */
    const d = domainOf(hist([[1.5, 1.2], [1.7, 1.4], [1.98, 1.6]]))

    expect(d.clipped).toBe(false)
    expect(d.lo).toBeLessThan(1.2)
    expect(d.hi).toBe(1.98)
  })

  it('tampoco recorta una media negativa mientras sea del mismo orden', () => {
    const d = domainOf(hist([[1.5, -0.4], [1.7, 0.3], [1.98, 1.1]]))
    expect(d.clipped).toBe(false)
    expect(d.lo).toBeLessThan(-0.4)
  })

  it('no colapsa cuando todo vale lo mismo', () => {
    /* Una búsqueda que converge en la primera generación deja best == mean
       constante; un span de cero haría una división por cero en la escala. */
    const d = domainOf(hist([[1.0, 1.0], [1.0, 1.0]]))
    expect(d.hi).toBeGreaterThan(d.lo)
    expect(Number.isFinite(d.lo)).toBe(true)
  })

  it('conserva el cero dentro del dominio cuando el mejor es negativo', () => {
    /* Con un fitness construido sobre el Sharpe fuera de muestra, cruzar el cero
       es la diferencia entre buscar algo y buscar nada: no puede quedarse fuera
       del gráfico. */
    const d = domainOf(hist([[-0.4, -3.0], [-0.2, -1.0], [0.3, -0.5]]))
    expect(d.lo).toBeLessThan(0)
    expect(d.hi).toBeGreaterThan(0)
  })
})

function progress(over: Partial<EvolutionProgress> = {}): EvolutionProgress {
  return {
    phase: 'evolving',
    generation: 9,
    generations_total: 25,
    history: hist([[1.5, -65.94], [1.7, 0.9], [1.98, 1.4]]),
    top: [{
      hash: 'a1', description: 'ENTRAR si RSI(14) < 30', fitness: 1.509,
      equity: [1, 1.2, 1.6, 2.07], total_return_pct: 107.4,
      max_drawdown_pct: 28, n_trades: 9,
    }],
    ...over,
  } as EvolutionProgress
}

describe('EvolutionLiveBoard', () => {
  it('avisa de que los retornos de las tarjetas son dentro de muestra', () => {
    render(<EvolutionLiveBoard progress={progress()} />)

    expect(screen.getAllByText(/dentro de muestra/).length).toBeGreaterThan(0)
    expect(screen.getByText(/inflados por construcción/)).toBeInTheDocument()
  })

  it('promete que al final se dirá qué fue de cada una', () => {
    /* Es la mitad del contrato: sin ella, el aviso solo desanima; con ella, el
       usuario sabe que no va a perder de vista lo que está mirando. */
    render(<EvolutionLiveBoard progress={progress()} />)
    expect(screen.getByText(/qué fue de cada una/)).toBeInTheDocument()
  })

  it('las tarjetas son las mejores de la búsqueda, no las de esta generación', () => {
    /* El título importa: antes decía «de la generación» y las tarjetas cambiaban
       enteras cada pocos segundos, así que una candidata con un +107 % se
       esfumaba sin haber sido superada por nada. */
    render(<EvolutionLiveBoard progress={progress()} />)
    expect(screen.getByText(/Mejores de la búsqueda hasta ahora/)).toBeInTheDocument()
  })

  it('marca en la tarjeta el lado del mercado cuando no es largo', () => {
    render(<EvolutionLiveBoard progress={progress({
      top: [{
        hash: 'b2', description: 'CORTO si RSI(14) > 70', fitness: 1.2, direction: 'short',
        equity: [1, 1.1], total_return_pct: 12.0, max_drawdown_pct: 8, n_trades: 14,
      }],
    })} />)

    expect(screen.getByText('corto')).toBeInTheDocument()
  })

  it('señala lo que quedó fuera de escala en vez de esconderlo', () => {
    render(<EvolutionLiveBoard progress={progress()} />)
    expect(screen.getByText(/fuera de escala \(mín\. real -65\.9\)/)).toBeInTheDocument()
  })

  it('espera a tener dos generaciones antes de dibujar una convergencia', () => {
    render(<EvolutionLiveBoard progress={progress({ history: hist([[1.0, 0.2]]) })} />)
    expect(screen.getByText(/Esperando las primeras generaciones/)).toBeInTheDocument()
  })
})
