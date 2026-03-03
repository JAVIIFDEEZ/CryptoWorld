/**
 * pages/AssetDetailPage.tsx — Detalle de un activo criptográfico.
 *
 * Responsabilidad: mostrar información detallada de un activo
 * e iniciar análisis técnicos sobre él.
 *
 * El símbolo del activo llega por parámetro de ruta (:symbol).
 *
 * Estructura base lista para ampliar con:
 *   - Gráfico de precio histórico
 *   - Indicadores técnicos calculados por el backend
 *   - Panel de resultados de análisis
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset, type AnalysisResult } from '@/services/analysisService'

type AnalysisType = 'RSI' | 'MACD' | 'SMA' | 'EMA' | 'BOLLINGER'

function AssetDetailPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()

  const [asset, setAsset] = useState<CryptoAsset | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisType>('RSI')
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const assets = await analysisService.getAssets()
        const found = assets.find((a) => a.symbol === symbol?.toUpperCase())
        if (!found) {
          navigate('/dashboard', { replace: true })
          return
        }
        setAsset(found)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [symbol, navigate])

  async function handleRunAnalysis() {
    if (!symbol) return
    setIsRunningAnalysis(true)
    try {
      const result = await analysisService.runAnalysis({
        asset_symbol: symbol.toUpperCase(),
        analysis_type: selectedAnalysis,
      })
      setAnalysisResult(result)
    } finally {
      setIsRunningAnalysis(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400 animate-pulse">
        Cargando...
      </div>
    )
  }

  if (!asset) return null

  const change = parseFloat(asset.price_change_24h ?? '0')
  const isPositive = change >= 0

  return (
    <div>
      {/* Breadcrumb */}
      <button
        onClick={() => navigate(-1)}
        className="text-slate-400 hover:text-slate-200 text-sm mb-6 flex items-center gap-1 transition-colors"
      >
        ← Volver al dashboard
      </button>

      {/* Header del activo */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-slate-700 flex items-center justify-center text-lg font-bold text-blue-400">
              {asset.symbol.slice(0, 2)}
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">{asset.name}</h1>
              <p className="text-slate-400 text-sm">{asset.symbol}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold font-mono text-white">
              ${parseFloat(asset.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
            </p>
            <p className={`text-sm font-mono mt-1 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? '▲' : '▼'} {Math.abs(change).toFixed(2)}% (24h)
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-6 pt-6 border-t border-slate-700">
          <Metric label="Cap. de mercado" value={asset.market_cap ? `$${(parseFloat(asset.market_cap) / 1e9).toFixed(2)}B` : '—'} />
          <Metric label="Volumen 24h" value={asset.volume_24h ? `$${(parseFloat(asset.volume_24h) / 1e9).toFixed(2)}B` : '—'} />
          <Metric label="Tendencia" value={asset.is_bullish_24h ? '📈 Alcista' : '📉 Bajista'} />
        </div>
      </div>

      {/* Panel de análisis */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-base font-semibold text-white mb-4">Análisis técnico</h2>

        <div className="flex flex-wrap gap-2 mb-4">
          {(['RSI', 'MACD', 'SMA', 'EMA', 'BOLLINGER'] as AnalysisType[]).map((type) => (
            <button
              key={type}
              onClick={() => setSelectedAnalysis(type)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                selectedAnalysis === type
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        <button
          onClick={handleRunAnalysis}
          disabled={isRunningAnalysis}
          className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {isRunningAnalysis ? 'Ejecutando...' : `Ejecutar análisis ${selectedAnalysis}`}
        </button>

        {analysisResult && (
          <div className="mt-4 bg-slate-700/50 rounded-lg p-4 font-mono text-xs text-slate-300">
            <p className="text-slate-400 mb-2">Resultado del análisis:</p>
            <pre>{JSON.stringify(analysisResult, null, 2)}</pre>
          </div>
        )}

        <p className="text-slate-500 text-xs mt-4">
          Los análisis cuantitativos completos se implementarán en fases posteriores del TFG.
        </p>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-slate-500 text-xs mb-0.5">{label}</p>
      <p className="text-white text-sm font-medium">{value}</p>
    </div>
  )
}

export default AssetDetailPage
