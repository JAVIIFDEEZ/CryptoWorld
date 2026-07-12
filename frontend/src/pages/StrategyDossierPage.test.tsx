/**
 * StrategyDossierPage.test.tsx — Documento de auditoría de estrategia.
 *
 * Verifica el documento puro (DossierDocument): identidad + ADN, evidencia
 * original, análisis fresco, track record y degradación honesta sin datos.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DossierDocument } from './StrategyDossierPage'
import type { StrategyDossier } from '@/services/strategyGeneratorService'

const DOSSIER: StrategyDossier = {
  status: 'OK',
  identity: {
    strategy_id: 7, name: 'Campeona', description: 'RSI(14) < 30 → RSI(14) > 70',
    spec: {
      entry: { combine: 'AND', conditions: [{ type: 'threshold', indicator: 'RSI', params: { window: 14 }, op: 'lt', threshold: 30 }] },
      exit: { combine: 'AND', conditions: [{ type: 'threshold', indicator: 'RSI', params: { window: 14 }, op: 'gt', threshold: 70 }] },
    },
    spec_hash: 'abc123', asset_symbol: 'BTC', asset_name: 'Bitcoin', interval: '1d',
    rank: 1, fitness: 1.234, status: 'validated', is_monitored: true,
    last_signal: 'HOLD', last_signal_at: null,
    generated_at: '2026-07-01T10:00:00Z', created_at: '2026-07-01T10:00:00Z',
  },
  stored_evidence: {
    robustness_metrics: {
      n_trades: 24, total_return_pct: 18, max_drawdown_pct: -9, exposure_pct: 40,
      sharpe: 1.5, sortino: 2.0, wf_efficiency: 0.8, mean_oos_sharpe: 1.1, pbo: 0.2,
      monte_carlo: { prob_profit_pct: 90, return_p5_pct: 2, return_p50_pct: 15 },
      lookahead_leaky: false, cross_consistency: 0.67,
    },
    gating_checks: { min_trades: true, no_lookahead: true, wf_efficiency: true, pbo: true, mc_p5_positive: false },
    holdout_metrics: { return_pct: 14.2, sharpe: 1.1, max_drawdown_pct: -8, n_trades: 6, win_rate_pct: 66, candles: 140 },
    note: 'evidencia original',
  },
  fresh_analysis: {
    available: true, candles: 500, data_source: 'binance',
    equity: { equity: [1, 1.02, 1.05, 1.1], total_return_pct: 10, max_drawdown_pct: -4, n_trades: 9 },
    walk_forward_matrix: {
      rows: [{ n_splits: 3, folds: [0.5, 0.8, 0.2], mean_oos_sharpe: 0.5, efficiency: 0.7 }],
      total_folds: 3, positive_folds: 3, stability_score: 1.0, note: 'nota wf',
    },
  },
  track_record: {
    accounts: [{
      account_id: 1, started_at: '2026-07-02T09:00:00Z', is_active: true,
      initial_capital: 10000, equity: 10500, total_return_pct: 5.0,
      realized_pnl: 500, in_position: false, live_enabled: false, decayed: false,
    }],
    note: 'nota tr',
  },
  note: 'No constituye consejo financiero.',
}

describe('DossierDocument', () => {
  it('pinta identidad, ADN y hash del spec', () => {
    render(<DossierDocument d={DOSSIER} />)
    expect(screen.getByText('RSI(14) < 30 → RSI(14) > 70')).toBeInTheDocument()
    expect(screen.getAllByText(/spec #abc123/).length).toBeGreaterThanOrEqual(2)  // cabecera y pie
    expect(screen.getByText('RSI(14) < 30')).toBeInTheDocument()   // ADN entrada
    expect(screen.getByText('RSI(14) > 70')).toBeInTheDocument()   // ADN salida
  })

  it('muestra la evidencia original con multi-activo y el holdout', () => {
    render(<DossierDocument d={DOSSIER} />)
    expect(screen.getByText('67%')).toBeInTheDocument()             // cross_consistency
    expect(screen.getByText(/\+14.2%/)).toBeInTheDocument()         // holdout
    expect(screen.getByText('Percentil 5 Monte Carlo positivo')).toBeInTheDocument()
  })

  it('muestra el análisis fresco y la estabilidad actual', () => {
    render(<DossierDocument d={DOSSIER} />)
    expect(screen.getByText(/Equity últimas 500 velas/)).toBeInTheDocument()
    expect(screen.getByText(/3\/3 tramos positivos \(100%\)/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Curva de equity/ })).toBeInTheDocument()
  })

  it('muestra el track record del usuario', () => {
    render(<DossierDocument d={DOSSIER} />)
    expect(screen.getByText('+5%')).toBeInTheDocument()
    expect(screen.getByText('▶ activa')).toBeInTheDocument()
  })

  it('degrada con honestidad sin análisis fresco', () => {
    const sinFresh = { ...DOSSIER, fresh_analysis: { available: false, note: 'Sin datos de BTC.' } }
    render(<DossierDocument d={sinFresh} />)
    expect(screen.getByText('Sin datos de BTC.')).toBeInTheDocument()
  })
})
