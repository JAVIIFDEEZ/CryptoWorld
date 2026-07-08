/**
 * services/portfolioService.ts — API calls para el módulo Portfolio.
 *
 * Endpoints legacy (compatibilidad):
 *   GET  /api/portfolio/            → Resumen net-position
 *   GET  /api/portfolio/trades/     → Historial de operaciones
 *   POST /api/portfolio/trades/     → Registrar nueva operación
 *   DELETE /api/portfolio/trades/:id/ → Eliminar operación
 *
 * Endpoints de posiciones explícitas (nuevos):
 *   GET  /api/portfolio/positions/            → Lista de posiciones abiertas/cerradas
 *   POST /api/portfolio/positions/            → Abrir nueva posición
 *   PATCH /api/portfolio/positions/:id/       → Actualizar etiqueta
 *   DELETE /api/portfolio/positions/:id/      → Eliminar posición (sin trades)
 *   POST /api/portfolio/positions/:id/add/    → Ampliar posición (AVCO)
 *   POST /api/portfolio/positions/:id/close/  → Cerrar posición (parcial o total)
 */

import apiClient from './api'

export interface PortfolioPosition {
  asset_symbol: string
  asset_name: string
  logo_url: string
  quantity: number
  avg_buy_price: number
  total_invested: number
  current_price: number
  current_value: number
  pnl_usd: number
  pnl_pct: number
  is_profit: boolean
  position_type: 'LONG' | 'SHORT'
}

export interface PortfolioSummary {
  total_invested_usd: number
  total_current_value_usd: number
  total_pnl_usd: number
  total_pnl_pct: number
  is_profit: boolean
  positions: PortfolioPosition[]
  long_count: number
  short_count: number
  total_long_invested_usd: number
  total_short_exposure_usd: number
}

export interface Trade {
  id: number
  asset_symbol: string
  asset_name: string
  trade_type: 'BUY' | 'SELL'
  quantity: number
  price_usd: number
  total_usd: number
  notes: string
  executed_at: string
  created_at: string
}

export interface AddTradePayload {
  asset_symbol: string
  trade_type: 'BUY' | 'SELL'
  quantity: number
  price_usd: number
  executed_at: string  // ISO 8601 datetime
  notes?: string
}

export interface TradeFilters {
  symbol?: string
  trade_type?: 'BUY' | 'SELL' | ''
  limit?: number
}

// ── Tipos para el modelo de posiciones explícitas ──────────────────────────

export interface Position {
  id: number
  asset_symbol: string
  asset_name: string
  logo_url: string | null
  direction: 'LONG' | 'SHORT'
  status: 'OPEN' | 'CLOSED'
  label: string
  avg_entry_price: string
  open_quantity: string
  initial_quantity: string
  current_price: string
  unrealized_pnl_usd: string
  unrealized_pnl_pct: string
  realized_pnl_usd: string
  total_pnl_usd: string
  is_profit: boolean
  opened_at: string
  closed_at: string | null
  trades_count: number
}

export interface PositionSummary {
  open_positions: Position[]
  closed_positions: Position[]
  total_unrealized_pnl_usd: string
  total_realized_pnl_usd: string
  open_long_count: number
  open_short_count: number
}

export interface OpenPositionPayload {
  asset_symbol: string
  direction: 'LONG' | 'SHORT'
  quantity: number
  entry_price: number
  opened_at: string   // ISO 8601
  label?: string
  notes?: string
}

export interface ClosePositionPayload {
  close_quantity: number
  close_price: number
  executed_at: string  // ISO 8601
  notes?: string
}

export interface AddToPositionPayload {
  quantity: number
  entry_price: number
  executed_at: string  // ISO 8601
  notes?: string
}

export interface PortfolioRiskExposure {
  symbol: string
  net_usd: number
  by_book: { manual: number; paper: number; live: number }
  in_var: boolean
}

export interface PortfolioRisk {
  status: 'OK' | 'EMPTY'
  exposures: PortfolioRiskExposure[]
  gross_usd: number
  net_usd: number
  long_usd?: number
  short_usd?: number
  top_concentration_pct?: number
  var?: {
    status: 'OK' | 'INSUFICIENTE'
    days: number
    var95_usd?: number
    cvar95_usd?: number
    var99_usd?: number
    cvar99_usd?: number
    worst_day_usd?: number
    note?: string
  }
  var_symbols_excluded?: string[]
  stress?: { window_days: number; impact_usd: number; shocks_pct: Record<string, number>; symbols_covered: number; symbols_total: number }[]
  history_days?: number
  note?: string
}

export const portfolioService = {
  /** Riesgo agregado del libro completo: exposición firmada, VaR/CVaR y stress. */
  /** Descarga un informe CSV (positions | risk) del usuario. */
  downloadReport: async (type: 'positions' | 'risk'): Promise<void> => {
    const resp = await apiClient.get('/portfolio/export/', {
      params: { type }, responseType: 'blob',
    })
    const url = window.URL.createObjectURL(resp.data as Blob)
    const a = document.createElement('a')
    a.href = url
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    a.download = `cryptoworld_${type}_${stamp}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  },

  getRisk: async (): Promise<PortfolioRisk> => {
    const { data } = await apiClient.get<PortfolioRisk>('/portfolio/risk/')
    return data
  },

  /** Obtener el precio actual de un activo por símbolo (null si no está en el catálogo) */
  getAssetPrice: async (symbol: string): Promise<number | null> => {
    try {
      const { data } = await apiClient.get('/assets/')
      const assets: Array<{ symbol: string; current_price: string }> = Array.isArray(data)
        ? data
        : (data.results ?? [])
      const found = assets.find(a => a.symbol.toUpperCase() === symbol.toUpperCase())
      return found ? parseFloat(found.current_price) : null
    } catch {
      return null
    }
  },

  /** Obtener resumen del portfolio con posiciones abiertas y PnL (legacy) */
  getSummary: async (): Promise<PortfolioSummary> => {
    const { data } = await apiClient.get('/portfolio/')
    return data
  },

  /** Listar historial de operaciones con filtros opcionales */
  getTrades: async (filters: TradeFilters = {}): Promise<Trade[]> => {
    const params = new URLSearchParams()
    if (filters.symbol) params.set('symbol', filters.symbol)
    if (filters.trade_type) params.set('trade_type', filters.trade_type)
    if (filters.limit) params.set('limit', String(filters.limit))
    const { data } = await apiClient.get(`/portfolio/trades/?${params}`)
    return data
  },

  /** Registrar una nueva operación (compra o venta) — legacy */
  addTrade: async (payload: AddTradePayload): Promise<Trade> => {
    const { data } = await apiClient.post('/portfolio/trades/', payload)
    return data
  },

  /** Eliminar una operación del historial */
  deleteTrade: async (tradeId: number): Promise<void> => {
    await apiClient.delete(`/portfolio/trades/${tradeId}/`)
  },

  // ── Posiciones explícitas ──────────────────────────────────────────

  /** Obtener todas las posiciones (OPEN + CLOSED) del usuario */
  getPositions: async (statusFilter?: 'OPEN' | 'CLOSED'): Promise<PositionSummary> => {
    const params = statusFilter ? `?status=${statusFilter}` : ''
    const { data } = await apiClient.get(`/portfolio/positions/${params}`)
    return data
  },

  /** Abrir una nueva posición LONG o SHORT */
  openPosition: async (payload: OpenPositionPayload): Promise<Position> => {
    const { data } = await apiClient.post('/portfolio/positions/', payload)
    return data
  },

  /** Ampliar una posición existente (recalcula AVCO) */
  addToPosition: async (positionId: number, payload: AddToPositionPayload): Promise<Position> => {
    const { data } = await apiClient.post(`/portfolio/positions/${positionId}/add/`, payload)
    return data
  },

  /** Cerrar una posición (parcial o total) */
  closePosition: async (positionId: number, payload: ClosePositionPayload): Promise<Position> => {
    const { data } = await apiClient.post(`/portfolio/positions/${positionId}/close/`, payload)
    return data
  },

  /** Actualizar la etiqueta de una posición */
  updatePositionLabel: async (positionId: number, label: string): Promise<Position> => {
    const { data } = await apiClient.patch(`/portfolio/positions/${positionId}/`, { label })
    return data
  },

  /** Eliminar una posición (sólo si no tiene trades) */
  deletePosition: async (positionId: number): Promise<void> => {
    await apiClient.delete(`/portfolio/positions/${positionId}/`)
  },
}
