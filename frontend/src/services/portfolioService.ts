/**
 * services/portfolioService.ts — API calls para el módulo Portfolio.
 *
 * Endpoints:
 *   GET  /api/portfolio/            → Resumen del portfolio con PnL
 *   GET  /api/portfolio/trades/     → Historial de operaciones
 *   POST /api/portfolio/trades/     → Registrar nueva operación
 *   DELETE /api/portfolio/trades/:id/ → Eliminar operación
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
}

export interface PortfolioSummary {
  total_invested_usd: number
  total_current_value_usd: number
  total_pnl_usd: number
  total_pnl_pct: number
  is_profit: boolean
  positions: PortfolioPosition[]
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

export const portfolioService = {
  /** Obtener resumen del portfolio con posiciones abiertas y PnL */
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

  /** Registrar una nueva operación (compra o venta) */
  addTrade: async (payload: AddTradePayload): Promise<Trade> => {
    const { data } = await apiClient.post('/portfolio/trades/', payload)
    return data
  },

  /** Eliminar una operación del historial */
  deleteTrade: async (tradeId: number): Promise<void> => {
    await apiClient.delete(`/portfolio/trades/${tradeId}/`)
  },
}
