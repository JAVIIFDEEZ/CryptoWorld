/**
 * pages/NewsPage.tsx — Feed de noticias de criptomonedas.
 *
 * Layout "revista": artículo destacado + grid de 2 columnas.
 * Fuente: CryptoCompare News API (a través del backend).
 */

import { useState, useEffect, useCallback } from 'react'
import { newsService, type NewsItem } from '../services/newsService'

type Sentiment = 'positive' | 'negative' | 'neutral' | ''

const SENTIMENT_CONFIG = {
  positive: {
    label: 'Positivo',
    icon: '↑',
    badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
    stat: 'text-emerald-400',
    statBg: 'bg-emerald-500/10 border-emerald-500/20',
    bar: 'bg-emerald-500',
    filter: 'bg-emerald-600 text-white border-emerald-600',
  },
  negative: {
    label: 'Negativo',
    icon: '↓',
    badge: 'bg-red-500/20 text-red-400 border-red-500/40',
    stat: 'text-red-400',
    statBg: 'bg-red-500/10 border-red-500/20',
    bar: 'bg-red-500',
    filter: 'bg-red-600 text-white border-red-600',
  },
  neutral: {
    label: 'Neutral',
    icon: '→',
    badge: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
    stat: 'text-slate-300',
    statBg: 'bg-slate-700/50 border-slate-600/50',
    bar: 'bg-slate-400',
    filter: 'bg-slate-600 text-white border-slate-600',
  },
} as const

function formatDate(iso: string): string {
  const d = new Date(iso)
  const diffMs = Date.now() - d.getTime()
  const diffH = Math.floor(diffMs / 3_600_000)
  if (diffH < 1) {
    const diffM = Math.floor(diffMs / 60_000)
    return diffM < 2 ? 'Ahora mismo' : `Hace ${diffM} min`
  }
  if (diffH < 24) return `Hace ${diffH}h`
  return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })
}

function SentimentBadge({ sentiment, size = 'sm' }: { sentiment: string; size?: 'sm' | 'md' }) {
  const cfg = SENTIMENT_CONFIG[sentiment as keyof typeof SENTIMENT_CONFIG] ?? SENTIMENT_CONFIG.neutral
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-medium ${
        size === 'md' ? 'text-xs px-3 py-1' : 'text-xs px-2 py-0.5'
      } ${cfg.badge}`}
    >
      {cfg.icon} {cfg.label}
    </span>
  )
}

function FeaturedCard({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col sm:flex-row rounded-2xl overflow-hidden border border-slate-700 hover:border-slate-500 bg-slate-800/60 transition-all duration-200 hover:shadow-2xl hover:shadow-black/50"
    >
      <div className="relative sm:w-5/12 h-52 sm:h-auto shrink-0 bg-slate-700/60 overflow-hidden">
        {item.imageurl ? (
          <img
            src={item.imageurl}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={e => {
              const el = e.target as HTMLImageElement
              el.style.display = 'none'
            }}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-blue-900/40 to-slate-800 flex items-center justify-center">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-20 text-slate-400"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8V6z"/></svg>
          </div>
        )}
        <span className="absolute top-3 left-3 text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-600/90 text-white backdrop-blur-sm shadow">
          Destacado
        </span>
      </div>
      <div className="flex flex-col justify-between p-5 sm:p-6 flex-1 min-w-0">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <SentimentBadge sentiment={item.sentiment} size="md" />
            {item.categories && (
              <span className="text-xs text-slate-500 truncate">
                {item.categories.split('|').slice(0, 3).join(' · ')}
              </span>
            )}
          </div>
          <h2 className="text-lg sm:text-xl font-bold text-white leading-snug mb-3 group-hover:text-blue-300 transition-colors line-clamp-3">
            {item.title}
          </h2>
          {item.body && (
            <p className="text-sm text-slate-400 line-clamp-3 leading-relaxed">{item.body}</p>
          )}
        </div>
        <div className="flex items-center gap-3 mt-5 pt-4 border-t border-slate-700/50">
          <span className="text-sm font-medium text-slate-300 truncate">{item.source}</span>
          <span className="text-slate-600 shrink-0">·</span>
          <span className="text-sm text-slate-500 shrink-0">{formatDate(item.published_at)}</span>
          <span className="ml-auto text-xs text-blue-400 group-hover:text-blue-300 transition-colors shrink-0">
            Leer más →
          </span>
        </div>
      </div>
    </a>
  )
}

function NewsCard({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col rounded-xl overflow-hidden border border-slate-700 hover:border-slate-500 bg-slate-800/50 hover:bg-slate-800 transition-all duration-200 hover:shadow-lg hover:shadow-black/30"
    >
      <div className="relative h-40 shrink-0 bg-slate-700/60 overflow-hidden">
        {item.imageurl ? (
          <img
            src={item.imageurl}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={e => {
              const el = e.target as HTMLImageElement
              el.style.display = 'none'
            }}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-blue-900/20 via-slate-700/80 to-slate-800 flex items-center justify-center">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-20 text-slate-400"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8V6z"/></svg>
          </div>
        )}
        <div className="absolute top-2 right-2">
          <SentimentBadge sentiment={item.sentiment} />
        </div>
      </div>
      <div className="flex flex-col flex-1 p-4">
        <h3 className="font-semibold text-white text-sm leading-snug line-clamp-2 mb-2 group-hover:text-blue-300 transition-colors">
          {item.title}
        </h3>
        {item.body && (
          <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed flex-1 mb-3">{item.body}</p>
        )}
        <div className="flex items-center gap-2 text-xs text-slate-500 mt-auto pt-3 border-t border-slate-700/50">
          <span className="font-medium text-slate-400 truncate">{item.source}</span>
          <span className="shrink-0">·</span>
          <span className="shrink-0">{formatDate(item.published_at)}</span>
        </div>
      </div>
    </a>
  )
}

function FeaturedSkeleton() {
  return (
    <div className="flex flex-col sm:flex-row rounded-2xl overflow-hidden border border-slate-700 bg-slate-800/50 animate-pulse">
      <div className="sm:w-5/12 h-52 sm:h-64 bg-slate-700/60 shrink-0" />
      <div className="flex-1 p-6 space-y-3">
        <div className="h-4 bg-slate-700 rounded w-24" />
        <div className="h-6 bg-slate-700 rounded w-4/5" />
        <div className="h-6 bg-slate-700 rounded w-3/5" />
        <div className="h-4 bg-slate-700/60 rounded w-full mt-2" />
        <div className="h-4 bg-slate-700/60 rounded w-3/4" />
        <div className="h-4 bg-slate-700/60 rounded w-2/3" />
      </div>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="rounded-xl overflow-hidden border border-slate-700 bg-slate-800/50 animate-pulse">
      <div className="h-40 bg-slate-700/60" />
      <div className="p-4 space-y-2">
        <div className="h-4 bg-slate-700 rounded w-3/4" />
        <div className="h-4 bg-slate-700 rounded w-1/2" />
        <div className="h-3 bg-slate-700/60 rounded w-full" />
        <div className="h-3 bg-slate-700/60 rounded w-2/3" />
      </div>
    </div>
  )
}

const INITIAL_DISPLAY = 13
const LOAD_MORE_STEP = 12

export default function NewsPage() {
  const [allItems, setAllItems] = useState<NewsItem[]>([])
  const [displayCount, setDisplayCount] = useState(INITIAL_DISPLAY)
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [activeSentiment, setActiveSentiment] = useState<Sentiment>('')

  const fetchNews = useCallback(async () => {
    setLoading(true)
    setError('')
    setDisplayCount(INITIAL_DISPLAY)
    try {
      const res = await newsService.getNews({
        q: search || undefined,
        sentiment: activeSentiment || undefined,
        limit: 50,
      })
      setAllItems(res.data ?? [])
      setSource(res.source ?? '')
    } catch {
      setError('Error al cargar las noticias. Comprueba la conexión.')
    } finally {
      setLoading(false)
    }
  }, [search, activeSentiment])

  useEffect(() => {
    const timer = setTimeout(fetchNews, 400)
    return () => clearTimeout(timer)
  }, [fetchNews])

  const visibleItems = allItems.slice(0, displayCount)
  const featured = visibleItems[0] ?? null
  const gridItems = visibleItems.slice(1)
  const hasMore = displayCount < allItems.length

  const sentimentCounts = {
    positive: allItems.filter(i => i.sentiment === 'positive').length,
    negative: allItems.filter(i => i.sentiment === 'negative').length,
    neutral: allItems.filter(i => i.sentiment === 'neutral').length,
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Noticias cripto</h1>
        <p className="text-slate-400 text-sm mt-1">
          Fuente: CryptoCompare
          {!loading && allItems.length > 0 && (
            <span className="ml-2 text-slate-500">· {allItems.length} artículos</span>
          )}
          {source && <span className="ml-1 text-slate-600">({source})</span>}
        </p>
      </header>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none select-none">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          </span>
          <input
            type="text"
            placeholder="Buscar: Bitcoin, DeFi, Ethereum…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-9 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors text-xs"
            >
              ×
            </button>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {(['', 'positive', 'negative', 'neutral'] as Sentiment[]).map(s => {
            const isActive = activeSentiment === s
            const cfg = s ? SENTIMENT_CONFIG[s] : null
            return (
              <button
                key={s === '' ? 'all' : s}
                onClick={() => setActiveSentiment(s)}
                className={`px-3 py-2.5 rounded-xl text-xs font-medium whitespace-nowrap border transition-all ${
                  isActive
                    ? s === ''
                      ? 'bg-blue-600 text-white border-blue-600'
                      : cfg!.filter
                    : 'bg-slate-800 text-slate-400 hover:text-white border-slate-700 hover:border-slate-500'
                }`}
              >
                {s === '' ? 'Todos' : `${cfg!.icon} ${cfg!.label}`}
              </button>
            )
          })}
        </div>
      </div>

      {!loading && allItems.length > 0 && (
        <div className="flex gap-3">
          {(['positive', 'negative', 'neutral'] as const).map(s => {
            const cfg = SENTIMENT_CONFIG[s]
            const count = sentimentCounts[s]
            const pct = allItems.length ? Math.round((count / allItems.length) * 100) : 0
            return (
              <button
                key={s}
                onClick={() => setActiveSentiment(activeSentiment === s ? '' : s)}
                className={`flex-1 rounded-xl border p-3 text-center transition-all hover:opacity-90 ${cfg.statBg} ${
                  activeSentiment === s ? 'ring-1 ring-offset-1 ring-offset-slate-900 ring-current' : ''
                }`}
              >
                <p className={`text-xl font-bold ${cfg.stat}`}>{count}</p>
                <p className="text-xs text-slate-400 mb-2">{cfg.label}s</p>
                <div className="h-1 rounded-full bg-slate-700/80 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${cfg.bar}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </button>
            )
          })}
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <FeaturedSkeleton />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="bg-red-900/20 border border-red-800/50 rounded-xl p-4 text-red-300 text-sm flex items-center gap-3">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && allItems.length === 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-300 font-medium">Sin resultados</p>
          <p className="text-slate-500 text-sm mt-1">No hay noticias para los filtros seleccionados.</p>
        </div>
      )}

      {!loading && !error && allItems.length > 0 && (
        <>
          {featured && <FeaturedCard item={featured} />}
          {gridItems.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {gridItems.map(item => (
                <NewsCard key={item.id || item.url} item={item} />
              ))}
            </div>
          )}
          {hasMore && (
            <div className="flex justify-center pt-2">
              <button
                onClick={() => setDisplayCount(c => c + LOAD_MORE_STEP)}
                className="px-8 py-3 rounded-xl bg-slate-800 border border-slate-700 hover:border-slate-500 hover:bg-slate-700/80 text-slate-300 hover:text-white text-sm font-medium transition-all"
              >
                Cargar más · {allItems.length - displayCount} restantes
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
