import { useEffect, useState } from 'react'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import AnalysisPanel from '@/components/AnalysisPanel'

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
      </header>

      {isLoadingAssets && (
        <p className="text-slate-400 text-sm animate-pulse">Cargando activos...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {!isLoadingAssets && assets.length > 0 && (
        <AnalysisPanel symbol={selectedSymbol} />
      )}
    </section>
  )
}

export default TechnicalAnalysisPage
