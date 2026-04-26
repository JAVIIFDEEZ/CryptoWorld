/**
 * services/newsService.ts — API calls para el módulo Noticias.
 *
 * Endpoint:
 *   GET /api/news/?q=&sentiment=&limit= → Feed de noticias cripto
 *
 * Proveedor: CryptoCompare News API
 */

import apiClient from './api'

export interface NewsItem {
  id: string
  title: string
  body: string
  url: string
  imageurl: string
  source: string
  published_at: string
  categories: string
  sentiment: 'positive' | 'negative' | 'neutral'
}

export interface NewsFeedResponse {
  total: number
  source: string
  data: NewsItem[]
}

export interface NewsFilters {
  q?: string
  sentiment?: 'positive' | 'negative' | 'neutral' | ''
  limit?: number
}

export const newsService = {
  /** Obtener feed de noticias con filtros opcionales */
  getNews: async (filters: NewsFilters = {}): Promise<NewsFeedResponse> => {
    const params = new URLSearchParams()
    if (filters.q) params.set('q', filters.q)
    if (filters.sentiment) params.set('sentiment', filters.sentiment)
    if (filters.limit) params.set('limit', String(filters.limit))
    const { data } = await apiClient.get(`/news/?${params}`)
    return data
  },
}
