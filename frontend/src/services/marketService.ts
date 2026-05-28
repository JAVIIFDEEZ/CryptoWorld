/**
 * services/marketService.ts — Servicio para datos de mercado.
 *
 * Encapsula las llamadas a:
 *   GET /api/assets/<symbol>/ohlcv/   — velas OHLCV desde Binance
 *   GET /api/market/overview/          — resumen global del mercado
 */

import apiClient from './api'

// ── Tipos ──────────────────────────────────────────────────────────

export interface OhlcvCandle {
  open_time: string   // ISO 8601
  open: string
  high: string
  low: string
  close: string
  volume: string
  source: string      // "binance" | "coingecko"
}

export interface OhlcvResponse {
  source: string       // "binance" | "coingecko"
  candles: OhlcvCandle[]
}

export interface MarketOverview {
  total_market_cap_usd: string
  total_volume_24h_usd: string
  btc_dominance_pct: string
  fear_greed_index: number
  updated_at: string
}

export type OhlcvInterval =
  | '1m' | '5m' | '15m' | '30m'
  | '1h' | '2h' | '4h' | '6h' | '12h'
  | '1d' | '1w'

// ── Servicio ───────────────────────────────────────────────────────

export const marketService = {
  /**
   * Obtener velas OHLCV para un activo.
   * GET /api/assets/<symbol>/ohlcv/?interval=<interval>&limit=<limit>
   * Fuente: Binance Public API (real, sin auth)
   */
  async getOhlcv(
    symbol: string,
    interval: OhlcvInterval = '1h',
    limit: number = 200,
  ): Promise<OhlcvResponse> {
    const { data } = await apiClient.get<OhlcvResponse>(
      `/assets/${symbol.toUpperCase()}/ohlcv/`,
      { params: { interval, limit } },
    )
    return data
  },

  /**
   * Obtener resumen global del mercado.
   * GET /api/market/overview/
   * Fuente: CoinGecko /global + Alternative.me Fear & Greed
   */
  async getMarketOverview(): Promise<MarketOverview> {
    const { data } = await apiClient.get<MarketOverview>('/market/overview/')
    return data
  },

  /**
   * Obtener precios de cierre diarios (últimos 7 días) para varios activos.
   * GET /api/assets/sparklines/?symbols=BTC,ETH,SOL
   * Útil para renderizar mini-sparklines en tablas y tarjetas.
   *
   * @param symbols - Array de símbolos en mayúsculas (máx. 10)
   * @returns Mapa símbolo → array de precios ordenados cronológicamente
   */
  async getSparklines(symbols: string[]): Promise<Record<string, number[]>> {
    if (symbols.length === 0) return {}
    const { data } = await apiClient.get<Record<string, number[]>>(
      '/assets/sparklines/',
      { params: { symbols: symbols.join(',') } },
    )
    return data
  },
}
