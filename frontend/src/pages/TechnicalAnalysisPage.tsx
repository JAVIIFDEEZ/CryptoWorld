import { useEffect, useState } from 'react'
import { analysisService, type AnalysisResult, type CryptoAsset } from '@/services/analysisService'

type AnalysisType = 'RSI' | 'MACD' | 'SMA' | 'EMA' | 'BOLLINGER'

const analysisTypes: AnalysisType[] = ['RSI', 'MACD', 'SMA', 'EMA', 'BOLLINGER']

function TechnicalAnalysisPage() {
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC')
  const [selectedType, setSelectedType] = useState<AnalysisType>('RSI')
  const [isLoadingAssets, setIsLoadingAssets] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)

  useEffect(() => {
    async function loadAssets() {
      try {
        const data = await analysisService.getAssets()
        setAssets(data)
        if (data.length > 0) {
          setSelectedSymbol(data[0].symbol)
        }
      } catch {
        setError('No se pudieron cargar los activos para analizar.')
      } finally {
        setIsLoadingAssets(false)
      }
    }

    loadAssets()
  }, [])

  async function handleRunAnalysis() {
    setError(null)
    setIsRunning(true)
    try {
      const response = await analysisService.runAnalysis({
        asset_symbol: selectedSymbol,
        analysis_type: selectedType,
      })
      setResult(response)
    } catch {
      setError('No se pudo ejecutar el analisis tecnico. Revisa la conexion con el backend.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Analisis Tecnico</h1>
        <p className="text-slate-400 text-sm mt-1">
          Integracion inicial del prototipo: ejecucion de indicadores sobre activos reales.
        </p>
      </header>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h2 className="text-base font-semibold text-white mb-4">Configurar analisis</h2>

        {isLoadingAssets && (
          <p className="text-slate-400 text-sm animate-pulse">Cargando activos...</p>
        )}

        {!isLoadingAssets && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label htmlFor="asset" className="block text-xs text-slate-400 mb-1.5 uppercase">Activo</label>
              <select
                id="asset"
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.symbol}>
                    {asset.symbol} - {asset.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="analysis" className="block text-xs text-slate-400 mb-1.5 uppercase">Indicador</label>
              <select
                id="analysis"
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as AnalysisType)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {analysisTypes.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              <button
                onClick={handleRunAnalysis}
                disabled={isRunning || assets.length === 0}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
              >
                {isRunning ? 'Ejecutando...' : 'Ejecutar analisis'}
              </button>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h2 className="text-base font-semibold text-white mb-4">Resultado</h2>
        {!result && (
          <p className="text-slate-400 text-sm">
            Aun no hay resultados. Ejecuta un analisis para ver la respuesta del backend.
          </p>
        )}
        {result && (
          <pre className="text-xs text-slate-200 bg-slate-900/60 border border-slate-700 rounded-lg p-4 overflow-auto">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>
    </section>
  )
}

export default TechnicalAnalysisPage
