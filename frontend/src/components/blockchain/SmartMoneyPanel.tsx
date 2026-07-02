/**
 * components/blockchain/SmartMoneyPanel.tsx — Radar de dinero inteligente.
 *
 * Ranking de direcciones cuyos depósitos/retiradas de exchanges ANTICIPARON el
 * precio (retiró antes de subir, depositó antes de caer), con acierto y retorno
 * capturado ponderados por tamaño sobre el histórico propio. Cada fila se puede
 * añadir a la vigilancia con un clic: si una wallet acierta, síguela.
 */

import { useEffect, useState } from 'react'
import {
  blockchainService,
  type SmartMoneyRadar,
} from '@/services/blockchainService'

function shorten(addr: string): string {
  return `${addr.slice(0, 8)}…${addr.slice(-6)}`
}

function fmtUsd(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

export default function SmartMoneyPanel({ chain = 'ethereum' }: Readonly<{ chain?: string }>) {
  const [data, setData] = useState<SmartMoneyRadar | null>(null)
  const [loading, setLoading] = useState(true)
  const [followed, setFollowed] = useState<Set<string>>(new Set())
  const [busyAddr, setBusyAddr] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    blockchainService.getSmartMoney(chain)
      .then((d) => setData(d.error ? null : d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [chain])

  async function follow(address: string) {
    if (!data || followed.has(address.toLowerCase())) return
    setBusyAddr(address)
    try {
      await blockchainService.addWatchedAddress(data.chain, address, 'smart money')
      setFollowed((s) => new Set(s).add(address.toLowerCase()))
    } catch { /* puede estar ya vigilada */ }
    finally { setBusyAddr(null) }
  }

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-amber-400">🎯</span>
        <h2 className="text-lg font-bold text-white">Smart money</h2>
        {data && <span className="ml-auto text-[10px] text-slate-500">últimos {data.window_days} días · horizonte {data.horizon_hours}h</span>}
      </div>
      <p className="text-slate-400 text-xs mb-4">
        Direcciones cuyos movimientos anticiparon el precio: retiró antes de subir, depositó antes de caer.
        Acierto ponderado por tamaño sobre el histórico propio.
      </p>

      {loading && <p className="text-slate-500 text-sm">Cargando…</p>}

      {!loading && data && data.leaderboard.length === 0 && (
        <p className="text-sm text-slate-500">
          Aún no hay direcciones con muestra suficiente (≥{data.min_moves} movimientos resueltos).
          El escáner acumula histórico cada 15 minutos; vuelve en unos días.
        </p>
      )}

      {!loading && data && data.leaderboard.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-700/60">
                <th className="py-1.5 pr-3">#</th>
                <th className="py-1.5 pr-3">Dirección</th>
                <th className="py-1.5 pr-3 text-right">Movs.</th>
                <th className="py-1.5 pr-3 text-right">Acierto</th>
                <th className="py-1.5 pr-3 text-right">Ret. capturado</th>
                <th className="py-1.5 pr-3 text-right">Volumen</th>
                <th className="py-1.5 text-right">Seguir</th>
              </tr>
            </thead>
            <tbody>
              {data.leaderboard.map((row, i) => {
                const isFollowed = followed.has(row.address.toLowerCase())
                return (
                  <tr key={row.address} className="border-b border-slate-800 last:border-0 hover:bg-slate-900/40">
                    <td className="py-2 pr-3 text-slate-500">{i + 1}</td>
                    <td className="py-2 pr-3 font-mono text-slate-200" title={row.address}>{shorten(row.address)}</td>
                    <td className="py-2 pr-3 text-right font-mono text-slate-300">{row.moves}</td>
                    <td className={`py-2 pr-3 text-right font-mono font-bold ${row.hit_rate >= 0.6 ? 'text-green-400' : row.hit_rate >= 0.4 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {(row.hit_rate * 100).toFixed(0)}%
                    </td>
                    <td className={`py-2 pr-3 text-right font-mono ${row.avg_captured_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {row.avg_captured_pct >= 0 ? '+' : ''}{row.avg_captured_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-slate-400">{fmtUsd(row.total_value_usd)}</td>
                    <td className="py-2 text-right">
                      <button
                        onClick={() => follow(row.address)}
                        disabled={busyAddr === row.address || isFollowed}
                        title={isFollowed ? 'En tu vigilancia' : 'Añadir a vigilancia'}
                        className={`text-sm transition-colors disabled:opacity-60 ${isFollowed ? 'text-fuchsia-400' : 'text-slate-500 hover:text-fuchsia-300'}`}
                      >
                        {isFollowed ? '✓👁' : '👁'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <p className="text-[10px] text-slate-600 mt-3">
          {data.movements_evaluated}/{data.movements_total} movimientos evaluados. {data.note}
        </p>
      )}
    </div>
  )
}
