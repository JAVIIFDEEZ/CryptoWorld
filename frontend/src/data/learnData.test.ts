/**
 * learnData.test.ts — Integridad del dataset educativo.
 *
 * El grafo 3D/2D depende de que las aristas referencien nodos existentes y de
 * que las L2 declaren una cadena de liquidación válida. Se verifica también que
 * el temario y el glosario estén bien formados.
 */

import { describe, it, expect } from 'vitest'
import {
  CHAINS, BRIDGES, LESSONS, GLOSSARY, allEdges, settlementEdges,
  connectionsOf, chainById, chainName,
} from './learnData'

const IDS = new Set(CHAINS.map((c) => c.id))

describe('learnData — cadenas', () => {
  it('tiene ids únicos', () => {
    expect(new Set(CHAINS.map((c) => c.id)).size).toBe(CHAINS.length)
  })

  it('cada L2/sidechain liquida en una cadena existente', () => {
    for (const c of CHAINS) {
      if (c.settlesOn) expect(IDS.has(c.settlesOn)).toBe(true)
    }
  })

  it('las L1 no declaran cadena de liquidación', () => {
    for (const c of CHAINS.filter((x) => x.category === 'L1')) {
      expect(c.settlesOn).toBeUndefined()
    }
  })

  it('el tamaño está normalizado en (0, 1]', () => {
    for (const c of CHAINS) {
      expect(c.size).toBeGreaterThan(0)
      expect(c.size).toBeLessThanOrEqual(1)
    }
  })
})

describe('learnData — aristas', () => {
  it('cada puente referencia nodos existentes', () => {
    for (const e of BRIDGES) {
      expect(IDS.has(e.from)).toBe(true)
      expect(IDS.has(e.to)).toBe(true)
    }
  })

  it('allEdges = liquidaciones + puentes', () => {
    expect(allEdges().length).toBe(settlementEdges().length + BRIDGES.length)
  })

  it('hay una arista de liquidación por cada cadena con settlesOn', () => {
    const withSettle = CHAINS.filter((c) => c.settlesOn).length
    expect(settlementEdges().length).toBe(withSettle)
    for (const e of settlementEdges()) expect(e.kind).toBe('settlement')
  })

  it('connectionsOf devuelve solo aristas que tocan la cadena', () => {
    const conns = connectionsOf('ethereum')
    expect(conns.length).toBeGreaterThan(0)
    for (const e of conns) expect(e.from === 'ethereum' || e.to === 'ethereum').toBe(true)
  })
})

describe('learnData — helpers', () => {
  it('chainById / chainName resuelven', () => {
    expect(chainById('ethereum')?.name).toBe('Ethereum')
    expect(chainName('bitcoin')).toBe('Bitcoin')
    expect(chainName('desconocida')).toBe('desconocida')
  })
})

describe('learnData — temario y glosario', () => {
  it('las lecciones tienen id único y secciones no vacías', () => {
    expect(new Set(LESSONS.map((l) => l.id)).size).toBe(LESSONS.length)
    for (const l of LESSONS) {
      expect(l.sections.length).toBeGreaterThan(0)
      for (const s of l.sections) expect(s.body.length).toBeGreaterThan(0)
      expect(l.minutes).toBeGreaterThan(0)
    }
  })

  it('el glosario no está vacío y define cada término', () => {
    expect(GLOSSARY.length).toBeGreaterThan(0)
    for (const g of GLOSSARY) expect(g.def.length).toBeGreaterThan(0)
  })
})
