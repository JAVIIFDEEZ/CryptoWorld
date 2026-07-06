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

export interface GlobeNewsItem {
  title: string
  url: string
  category: string
  category_name: string
  sentiment: string
  published_at: string | null
}

export interface GlobeMarker {
  region: string
  name: string
  lat: number
  lon: number
  count: number
  importance: number
  categories: Record<string, number>
  top_category: string
  items: GlobeNewsItem[]
}

export interface NewsGlobe {
  markers: GlobeMarker[]
  located: number
  unlocated: number
  total: number
  note: string
  error?: string
}

export const newsService = {
  /** Noticias importantes clasificadas por región del mundo (globo 3D). */
  getNewsGlobe: async (): Promise<NewsGlobe> => {
    const { data } = await apiClient.get<NewsGlobe>('/news/globe/')
    return data
  },

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
