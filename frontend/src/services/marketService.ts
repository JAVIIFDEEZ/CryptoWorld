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

/**
 * Mapa de correlaciones de la cesta.
 *
 * Tres campos que NO son decorativos y que la interfaz tiene obligación de usar:
 *
 *  · `cell_se_z` — error típico de cada celda en el espacio de Fisher. Con
 *    ventana 90 vale ~0,11, así que dos celdas que difieran en menos que eso son
 *    la misma celda pintada distinta. Pintar el degradado sin enseñar este
 *    número es mentir con un gradiente.
 *  · `delta_beyond_noise` — qué celdas cambiaron más de lo que explica el ruido.
 *    NO lleva corrección por multiplicidad: son n(n−1)/2 comparaciones, así que
 *    sirve para dirigir la mirada y no para afirmar.
 *  · `eigen` — el resumen que se lee cuando nadie mira la matriz: qué fracción
 *    de la varianza explica un único factor y cuántas apuestas independientes
 *    hay de verdad.
 */
export interface CorrelationMap {
  verdict: 'CONCENTRADO' | 'INTERMEDIO' | 'REPARTIDO' | 'SIN_DATOS'
  labels: string[]
  matrix: number[][]
  window: number
  devolatilized: boolean
  returns_used?: number
  warmup_returns_dropped?: number
  cell_se_z: number
  average_correlation: number | null
  eigen: {
    n: number
    top_share: number | null
    effective_bets: number | null
    eigenvalues?: number[]
  }
  ordering?: string
  reference_window?: number
  reference_matrix?: number[][]
  delta?: number[][]
  delta_beyond_noise?: boolean[][]
  delta_threshold_z?: number
  pairs_beyond_noise?: number
  reference_average_correlation?: number | null
  reference_eigen?: CorrelationMap['eigen']
  delta_note?: string
  reference_note?: string
  interval?: string
  missing?: string[]
  candles_aligned?: number
  first?: string
  last?: string
  note: string
  limits?: string
}

export interface FxRates {
  base: 'usd'
  rates: Record<string, number>
  source: 'coingecko' | 'fallback'
  updated_at: string
}

export type OhlcvInterval =
  | '1m' | '5m' | '15m' | '30m'
  | '1h' | '2h' | '4h' | '6h' | '12h'
  | '1d' | '1w'

export interface AssetInfo {
  homepage: string | null
  whitepaper: string | null
  twitter: string | null
  reddit: string | null
  telegram: string | null
  github: string | null
  ath: number | null
  ath_date: string | null
  circulating_supply: number | null
  max_supply: number | null
  categories: string[]
  description: string | null
}

// ── Servicio ───────────────────────────────────────────────────────

// ── Caché en memoria con TTL ───────────────────────────────────────
// Evita re-fetches innecesarios durante la misma sesión de navegación.
const _cache = new Map<string, { data: unknown; expires: number }>()
function _cGet<T>(key: string): T | null {
  const entry = _cache.get(key)
  if (!entry || Date.now() > entry.expires) { _cache.delete(key); return null }
  return entry.data as T
}
function _cSet(key: string, data: unknown, ttlMs: number): void {
  _cache.set(key, { data, expires: Date.now() + ttlMs })
}

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
   * Caché en memoria 5 min (el backend también cachea en Redis).
   */
  async getMarketOverview(): Promise<MarketOverview> {
    const cached = _cGet<MarketOverview>('market_overview')
    if (cached) return cached
    const { data } = await apiClient.get<MarketOverview>('/market/overview/')
    _cSet('market_overview', data, 5 * 60_000)
    return data
  },

  /**
   * Obtener precios de cierre diarios (últimos 7 días) para varios activos.
   * GET /api/assets/sparklines/?symbols=BTC,ETH,SOL
   * Útil para renderizar mini-sparklines en tablas y tarjetas.
   *
   * El backend acepta un máximo de 10 símbolos por petición; este método
   * divide el array en chunks y consolida los resultados automáticamente.
   *
   * @param symbols - Array de símbolos en mayúsculas (sin límite de tamaño)
   * @returns Mapa símbolo → array de precios ordenados cronológicamente
   */
  async getSparklines(symbols: string[]): Promise<Record<string, number[]>> {
    if (symbols.length === 0) return {}
    const sortedKey = 'sparklines:' + [...symbols].sort((a, b) => a.localeCompare(b)).join(',')
    const cached = _cGet<Record<string, number[]>>(sortedKey)
    if (cached) return cached
    const CHUNK_SIZE = 10
    const chunks: string[][] = []
    for (let i = 0; i < symbols.length; i += CHUNK_SIZE) {
      chunks.push(symbols.slice(i, i + CHUNK_SIZE))
    }
    const results = await Promise.all(
      chunks.map((chunk) =>
        apiClient
          .get<Record<string, number[]>>('/assets/sparklines/', {
            params: { symbols: chunk.join(',') },
          })
          .then((r) => r.data)
          .catch((err): Record<string, number[]> => {
            // Degradacion con gracia: la UI no se rompe si falla un grupo,
            // pero registramos el motivo para no ocultar errores del backend.
            console.warn('[getSparklines] no se pudo cargar el grupo', chunk, err)
            return {}
          }),
      ),
    )
    const merged = Object.assign({}, ...results)
    _cSet(sortedKey, merged, 60 * 60_000)  // 1 hora
    return merged
  },

  /**
   * Información de proyecto de un activo (enlaces, ATH, suministro, categorías).
   * GET /api/assets/<symbol>/info/
   */
  async getAssetInfo(symbol: string): Promise<AssetInfo> {
    const { data } = await apiClient.get<AssetInfo>(`/assets/${symbol}/info/`)
    return data
  },

  /**
   * Tasas de cambio USD→EUR/GBP para mostrar precios en la moneda preferida.
   * GET /api/market/fx/
   * Caché en memoria 1h (el backend también cachea en Redis).
   */
  async getFxRates(): Promise<FxRates> {
    const cached = _cGet<FxRates>('fx_rates')
    if (cached) return cached
    const { data } = await apiClient.get<FxRates>('/market/fx/')
    _cSet('fx_rates', data, 60 * 60_000)
    return data
  },

  /**
   * Mapa de correlaciones de la cesta, ordenado por conglomerados.
   * GET /api/market/correlation-map/
   *
   * Caché en memoria de 10 min, la misma que aplica el backend: la matriz se
   * mueve en días y recalcularla en cada render sería gasto sin información.
   */
  async getCorrelationMap(params?: {
    symbols?: string[]
    interval?: string
    window?: number
    referenceWindow?: number
  }): Promise<CorrelationMap> {
    const query: Record<string, string | number> = {}
    if (params?.symbols?.length) query.symbols = params.symbols.join(',')
    if (params?.interval) query.interval = params.interval
    if (params?.window) query.window = params.window
    if (params?.referenceWindow) query.reference_window = params.referenceWindow

    const key = `corr_map_${JSON.stringify(query)}`
    const cached = _cGet<CorrelationMap>(key)
    if (cached) return cached
    const { data } = await apiClient.get<CorrelationMap>('/market/correlation-map/', {
      params: query,
    })
    _cSet(key, data, 10 * 60_000)
    return data
  },
}
