/**
 * services/dataHealthService.ts — Salud del almacén histórico OHLCV.
 *
 * Endpoint: GET /api/data/health/
 */

import apiClient from './api'

export type SeriesStatus = 'SANO' | 'CON_HUECOS' | 'DESACTUALIZADO' | 'VACIO'

export interface OhlcvSeriesHealth {
  symbol: string
  interval: string
  candles: number
  gaps: number
  missing_candles: number
  first: number | null
  last: number | null
  completeness_pct: number
  freshness_hours: number | null
  fresh: boolean
  status: SeriesStatus
}

export interface DataHealthSummary {
  series: number
  healthy_pct: number
  with_gaps: number
  stale: number
  total_candles: number
  grade: 'EXCELENTE' | 'ACEPTABLE' | 'DEFICIENTE' | 'SIN_DATOS'
}

export interface DataHealth {
  status: 'OK' | 'EMPTY'
  series: OhlcvSeriesHealth[]
  summary: DataHealthSummary
  note?: string
}

export const dataHealthService = {
  get: async (): Promise<DataHealth> => {
    const { data } = await apiClient.get<DataHealth>('/data/health/')
    return data
  },
}
