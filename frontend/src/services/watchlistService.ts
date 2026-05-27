import api from './api';

export interface WatchlistItem {
  symbol: string;
  name: string;
  logo_url: string | null;
  current_price: string;
  price_change_24h: string;
  is_bullish_24h: boolean;
  added_at: string;
}

/** GET /api/watchlist/ — Obtener la watchlist del usuario autenticado. */
export async function getWatchlist(): Promise<WatchlistItem[]> {
  const response = await api.get<WatchlistItem[]>('/watchlist/');
  return response.data;
}

/** POST /api/watchlist/ — Añadir un activo a la watchlist. */
export async function addToWatchlist(symbol: string): Promise<void> {
  await api.post('/watchlist/', { symbol });
}

/** DELETE /api/watchlist/<symbol>/ — Eliminar un activo de la watchlist. */
export async function removeFromWatchlist(symbol: string): Promise<void> {
  await api.delete(`/watchlist/${symbol}/`);
}
