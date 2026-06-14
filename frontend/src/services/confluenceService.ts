/**
 * services/confluenceService.ts — Ficha de confluencia técnica de un activo.
 *
 * Consume el endpoint REST autenticado GET /api/assets/<symbol>/confluence/
 * (misma lógica de dominio que la landing SEO pública). Además expone el
 * helper que construye la URL de la landing pública, que NO vive en el
 * router de la SPA sino en el backend:
 *   - producción: Vercel proxea /cripto/* a Railway → URL relativa
 *   - desarrollo: no hay proxy → hay que apuntar al backend (localhost:8000)
 */

import apiClient from './api'

// ── Tipos (espejo del ConfluenceCardDTO del backend) ───────────────

export interface SrLevel {
  level: number
  touches: number
  distance_pct: number
}

export interface FiboLevel {
  ratio: number
  label: string
  price: number
}

export interface ConfluenceIndicator {
  name: string
  value: number | string
  signal: string
}

export interface ConfluenceCard {
  symbol: string
  name: string
  slug: string
  logo_url: string | null
  last_price: number
  generated_at: string
  interval: string
  data_source: string
  trend: {
    trend: 'ALCISTA' | 'LATERAL' | 'BAJISTA'
    sma_period: number
    sma_value: number
    price_vs_sma_pct: number
    ema_period: number
    ema_slope_pct: number
  }
  support_resistance: {
    supports: SrLevel[]
    resistances: SrLevel[]
    pivot_window: number
  }
  fibonacci: {
    swing_high: number
    swing_low: number
    direction: 'ALCISTA' | 'BAJISTA'
    lookback: number
    levels: FiboLevel[]
    nearest_level: FiboLevel | null
  }
  signals: {
    indicators: ConfluenceIndicator[]
    summary: {
      verdict: string
      score: number
      buy_count: number
      sell_count: number
      neutral_count: number
      total: number
    }
    last_price: number
  }
  verdict: {
    verdict: string
    confidence_pct: number
    confidence_level: 'ALTA' | 'MEDIA' | 'BAJA'
    trend_agrees: boolean
  }
  narrative: string
  analysis_paragraphs: string[]
}

/**
 * URL de la landing pública de un activo.
 *
 * Deriva el origen del backend de VITE_API_URL quitando el sufijo /api:
 *   "http://localhost:8000/api" → "http://localhost:8000/cripto/<slug>"
 *   "/api" (prod, vía proxy)    → "/cripto/<slug>"
 */
export function publicLandingUrl(slug: string): string {
  const apiBase = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/api\/?$/, '')
  return `${apiBase}/cripto/${slug}`
}

export const confluenceService = {
  /**
   * Ficha de confluencia de un activo.
   * GET /api/assets/<symbol>/confluence/
   */
  async getConfluence(symbol: string): Promise<ConfluenceCard> {
    const { data } = await apiClient.get<ConfluenceCard>(
      `/assets/${symbol.toUpperCase()}/confluence/`,
    )
    return data
  },
}
