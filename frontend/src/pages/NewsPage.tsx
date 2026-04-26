/**
 * pages/NewsPage.tsx — Feed de noticias de criptomonedas.
 *
 * Fuente: CryptoCompare News API (a través del backend)
 * Permite filtrar por término de búsqueda y sentimiento.
 */

import { useState, useEffect, useCallback } from 'react'
import { newsService, type NewsItem } from '../services/newsService'

type Sentiment = 'positive' | 'negative' | 'neutral' | ''

const SENTIMENT_STYLES: Record<Exclude<Sentiment, ''>, string> = {
  positive: 'bg-green-900/40 text-green-400 border-green-700/50',
  negative: 'bg-red-900/40 text-red-400 border-red-700/50',
  neutral: 'bg-gray-700/60 text-gray-300 border-gray-600/50',
}

const SENTIMENT_LABELS: Record<Exclude<Sentiment, ''>, string> = {
  positive: '↑ Positivo',
  negative: '↓ Negativo',
  neutral: '→ Neutral',
}

function NewsCard({ item }: { item: NewsItem }) {
  const sentiment = item.sentiment as Exclude<Sentiment, ''>
  const style = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral
  const label = SENTIMENT_LABELS[sentiment] ?? '→ Neutral'

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-gray-800 hover:bg-gray-750 rounded-xl overflow-hidden border border-gray-700 hover:border-gray-600 transition-colors"
    >
      <div className="flex gap-4 p-4">
        {item.imageurl && (
          <img
            src={item.imageurl}
            alt=""
            className="w-20 h-20 object-cover rounded-lg shrink-0"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-1">
            <h3 className="font-semibold text-white text-sm leading-snug line-clamp-2">
              {item.title}
            </h3>
            <span className={`shrink-0 text-xs px-2 py-0.5 rounded border ${style}`}>
              {label}
            </span>
          </div>
          <p className="text-xs text-gray-400 line-clamp-2 mb-2">{item.body}</p>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="font-medium text-gray-400">{item.source}</span>
            <span>·</span>
            <span>
              {new Date(item.published_at).toLocaleString('es-ES', {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </span>
            {item.categories && (
              <>
                <span>·</span>
                <span>{item.categories.split('|').slice(0, 2).join(', ')}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </a>
  )
}

export default function NewsPage() {
  const [items, setItems] = useState<NewsItem[]>([])
  const [total, setTotal] = useState(0)
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [sentiment, setSentiment] = useState<Sentiment>('')
  const [limit] = useState(30)

  const fetchNews = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await newsService.getNews({
        q: search || undefined,
        sentiment: sentiment || undefined,
        limit,
      })
      setItems(res.data)
      setTotal(res.total)
      setSource(res.source)
    } catch {
      setError('Error al cargar las noticias')
    } finally {
      setLoading(false)
    }
  }, [search, sentiment, limit])

  // Debounce búsqueda
  useEffect(() => {
    const timer = setTimeout(fetchNews, 400)
    return () => clearTimeout(timer)
  }, [fetchNews])

  const sentimentCounts = {
    positive: items.filter(i => i.sentiment === 'positive').length,
    negative: items.filter(i => i.sentiment === 'negative').length,
    neutral: items.filter(i => i.sentiment === 'neutral').length,
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-4xl mx-auto">
        {/* Cabecera */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Noticias cripto</h1>
          <p className="text-gray-400 text-sm mt-1">
            Fuente: CryptoCompare · {total > 0 ? `${total} noticias` : ''}
            {source && <span className="ml-2 text-gray-500">({source})</span>}
          </p>
        </div>

        {/* Controles */}
        <div className="flex flex-col sm:flex-row gap-3 mb-5">
          <input
            type="text"
            placeholder="Buscar: Bitcoin, Ethereum, DeFi…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <div className="flex gap-2">
            {(['', 'positive', 'negative', 'neutral'] as Sentiment[]).map(s => (
              <button
                key={s ?? 'all'}
                onClick={() => setSentiment(s)}
                className={`px-3 py-2 rounded-xl text-xs font-medium whitespace-nowrap ${
                  sentiment === s
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-700'
                }`}
              >
                {s === '' ? 'Todos' : SENTIMENT_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        {/* Estadísticas de sentimiento */}
        {!loading && items.length > 0 && (
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div className="bg-green-900/20 border border-green-800/40 rounded-xl p-3 text-center">
              <p className="text-xl font-bold text-green-400">{sentimentCounts.positive}</p>
              <p className="text-xs text-gray-400 mt-0.5">Positivas</p>
            </div>
            <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-3 text-center">
              <p className="text-xl font-bold text-red-400">{sentimentCounts.negative}</p>
              <p className="text-xs text-gray-400 mt-0.5">Negativas</p>
            </div>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-3 text-center">
              <p className="text-xl font-bold text-gray-300">{sentimentCounts.neutral}</p>
              <p className="text-xs text-gray-400 mt-0.5">Neutrales</p>
            </div>
          </div>
        )}

        {loading && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="bg-gray-800 rounded-xl p-8 text-center text-gray-400">
            <p>No se encontraron noticias para los filtros seleccionados.</p>
          </div>
        )}

        <div className="space-y-3">
          {items.map(item => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  )
}
