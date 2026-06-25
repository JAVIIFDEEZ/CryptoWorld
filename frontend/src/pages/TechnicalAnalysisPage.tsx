import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import AnalysisPanel from '@/components/analysis/AnalysisPanel'
import RobustnessPanel from '@/components/analysis/RobustnessPanel'
import Skeleton from '@/components/ui/Skeleton'

function TechnicalAnalysisPage() {
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC')
  const [isLoadingAssets, setIsLoadingAssets] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadAssets() {
      try {
        const data = await analysisService.getAssets()
        setAssets(data)
        if (data.length > 0) setSelectedSymbol(data[0].symbol)
      } catch {
        setError('No se pudieron cargar los activos.')
      } finally {
        setIsLoadingAssets(false)
      }
    }
    loadAssets()
  }, [])

  return (
    <section className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end gap-4">
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-white">Análisis Técnico</h1>
          <p className="text-slate-400 text-sm mt-1">
            Indicadores, señales, predicción ML, patrones de velas y backtesting sobre datos reales de mercado.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Precio actual del activo seleccionado */}
          {(() => {
            const selectedAsset = assets.find(a => a.symbol === selectedSymbol)
            if (!selectedAsset) return null
            const change = Number.parseFloat(selectedAsset.price_change_24h ?? '0')
            return (
              <div className="flex items-center gap-3 bg-slate-800 rounded-lg px-4 py-2 border border-slate-700">
                {selectedAsset.logo_url && (
                  <img src={selectedAsset.logo_url} alt={selectedAsset.symbol} className="w-6 h-6 rounded-full" />
                )}
                <div>
                  <p className="text-[10px] text-slate-500 leading-none">{selectedAsset.name}</p>
                  <p className="text-sm font-bold font-mono text-white">
                    ${Number.parseFloat(selectedAsset.current_price ?? '0').toLocaleString()}
                  </p>
                </div>
                <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                  change >= 0 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
                }`}>
                  {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                </span>
              </div>
            )
          })()}

          {/* Selector de activo */}
          {!isLoadingAssets && assets.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 uppercase">Activo</span>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {assets.map((a) => (
                  <option key={a.id} value={a.symbol}>
                    {a.symbol} — {a.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </header>

      {isLoadingAssets && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-72 rounded-xl" />
        </div>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {!isLoadingAssets && assets.length > 0 && (
        <>
          <AnalysisPanel symbol={selectedSymbol} />
          <RobustnessPanel symbol={selectedSymbol} />

          {/* Puente al generador genético: descubrir estrategias nuevas */}
          <Link
            to="/strategies"
            className="group flex items-center gap-4 bg-gradient-to-r from-blue-600/10 to-purple-600/10 hover:from-blue-600/20 hover:to-purple-600/20 border border-blue-500/30 rounded-xl p-4 transition-colors"
          >
            <span className="text-2xl">🧬</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">¿No sabes qué estrategia usar?</p>
              <p className="text-xs text-slate-400">
                Deja que el algoritmo genético evolucione y valide estrategias robustas sobre {selectedSymbol}.
              </p>
            </div>
            <span className="text-blue-300 group-hover:translate-x-0.5 transition-transform shrink-0">Generar →</span>
          </Link>
        </>
      )}
    </section>
  )
}

export default TechnicalAnalysisPage
