/**
 * hooks/queries/useMarketData.ts — Capa de datos de mercado con TanStack Query.
 *
 * Patrón de referencia de la migración: cada recurso HTTP se expone como un
 * hook con su queryKey; las vistas dejan de orquestar useEffect + useState y
 * pasan a declarar QUÉ datos necesitan. La caché es compartida: navegar de
 * Dashboard a Mercado no re-pide los activos si tienen menos de 30 s.
 *
 * Las mutaciones (watchlist) actualizan la caché de forma optimista y
 * revierten si el servidor falla: la estrella responde al instante.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService } from '@/services/marketService'
import { addToWatchlist, getWatchlist, removeFromWatchlist } from '@/services/watchlistService'

export const marketKeys = {
  assets: ['assets'] as const,
  sparklines: (symbols: string[]) => ['sparklines', ...symbols] as const,
  watchlist: ['watchlist'] as const,
}

/** Catálogo completo de activos. */
export function useAssets() {
  return useQuery<CryptoAsset[]>({
    queryKey: marketKeys.assets,
    queryFn: () => analysisService.getAssets(),
  })
}

/** Sparklines 7d de un lote de símbolos (mapa symbol → serie). */
export function useSparklines(symbols: string[]) {
  return useQuery<Record<string, number[]>>({
    queryKey: marketKeys.sparklines(symbols),
    queryFn: () => marketService.getSparklines(symbols),
    enabled: symbols.length > 0,
    staleTime: 5 * 60_000,   // las series de 7 días cambian despacio
  })
}

/** Símbolos en la watchlist del usuario. Si no está autenticado, conjunto vacío. */
export function useWatchlist() {
  return useQuery<string[]>({
    queryKey: marketKeys.watchlist,
    queryFn: async () => {
      try {
        const items = await getWatchlist()
        return items.map((i) => i.symbol)
      } catch {
        return []   // sin sesión: watchlist vacía, sin error en la UI
      }
    },
  })
}

/** Añadir/quitar de la watchlist con actualización optimista y rollback. */
export function useToggleWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ symbol, inWatchlist }: { symbol: string; inWatchlist: boolean }) => {
      if (inWatchlist) await removeFromWatchlist(symbol)
      else await addToWatchlist(symbol)
    },
    onMutate: async ({ symbol, inWatchlist }) => {
      await qc.cancelQueries({ queryKey: marketKeys.watchlist })
      const previous = qc.getQueryData<string[]>(marketKeys.watchlist)
      qc.setQueryData<string[]>(marketKeys.watchlist, (old = []) =>
        inWatchlist ? old.filter((s) => s !== symbol) : [...old, symbol],
      )
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous !== undefined) qc.setQueryData(marketKeys.watchlist, ctx.previous)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: marketKeys.watchlist })
    },
  })
}
