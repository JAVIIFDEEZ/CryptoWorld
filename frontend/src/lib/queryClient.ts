/**
 * lib/queryClient.ts — Cliente global de TanStack Query.
 *
 * Capa de datos declarativa: caché compartida entre vistas, deduplicación de
 * peticiones concurrentes, revalidación al volver a la pestaña y reintentos
 * con backoff. Los valores por defecto están pensados para datos de mercado:
 *   · staleTime 30 s — un precio de hace 20 s sigue siendo útil; evita
 *     re-pedir lo mismo al navegar entre páginas.
 *   · gcTime 5 min — la caché sobrevive a la navegación pero no crece sin fin.
 *   · retry 1 — un reintento (los errores de red transitorios se curan solos;
 *     los 4xx no se reintentan nunca).
 */

import { QueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        // Los errores del cliente (4xx: auth, validación, not found) son
        // deterministas: reintentar solo desperdicia peticiones.
        if (isAxiosError(error)) {
          const status = error.response?.status ?? 0
          if (status >= 400 && status < 500) return false
        }
        return failureCount < 1
      },
    },
  },
})
