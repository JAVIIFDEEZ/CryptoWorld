/**
 * services/tradingService.ts — Trading real multi-exchange (ccxt).
 *
 * Ejecución MANUAL: conexiones de exchange (claves cifradas en el backend,
 * testnet por defecto), balance, órdenes market/limit y cancelación. La API
 * nunca devuelve credenciales.
 */

import apiClient from './api'

export type ExchangeId = 'binance' | 'kraken' | 'coinbase' | 'bybit' | 'okx'

export const EXCHANGES: { id: ExchangeId; label: string; sandbox: boolean }[] = [
  { id: 'binance', label: 'Binance', sandbox: true },
  { id: 'bybit', label: 'Bybit', sandbox: true },
  { id: 'okx', label: 'OKX', sandbox: true },
  { id: 'kraken', label: 'Kraken', sandbox: false },
  { id: 'coinbase', label: 'Coinbase Advanced', sandbox: false },
]

export interface ExchangeConnection {
  id: number
  exchange: ExchangeId
  label: string | null
  is_testnet: boolean
  is_active: boolean
  last_used_at: string | null
  created_at: string
  error?: string
}

export interface BrokerBalanceRow {
  asset: string
  total: number
  free: number
  used: number
}

export interface BrokerBalance {
  connection: ExchangeConnection
  balances: BrokerBalanceRow[]
  error?: string
}

export interface BrokerOrder {
  id: string
  symbol: string | null
  side: 'buy' | 'sell' | null
  type: string | null
  amount: number | null
  price: number | null
  filled: number | null
  status: string | null
  datetime: string | null
}

export interface PlaceOrderResult {
  order: BrokerOrder
  is_testnet: boolean
  error?: string
}

export interface LiveRiskPolicy {
  daily_loss_limit_usd: number | null
  max_concentration_pct?: number | null
  realized_today_usd?: number
}

export const tradingService = {
  /** Política de riesgo OMS: límite de pérdida diaria y de concentración. */
  getRiskPolicy: async (): Promise<LiveRiskPolicy> => {
    const { data } = await apiClient.get<LiveRiskPolicy>('/trading/risk-policy/')
    return data
  },

  /** Actualiza los campos indicados de la política (solo se envían los presentes). */
  setRiskPolicy: async (patch: Partial<Pick<LiveRiskPolicy, 'daily_loss_limit_usd' | 'max_concentration_pct'>>): Promise<LiveRiskPolicy> => {
    const { data } = await apiClient.put<LiveRiskPolicy>('/trading/risk-policy/', patch)
    return data
  },

  /** Conexiones del usuario (sin credenciales). */
  async listConnections(): Promise<ExchangeConnection[]> {
    const { data } = await apiClient.get<{ count: number; results: ExchangeConnection[] }>('/trading/connections/')
    return data.results
  },

  /** Conecta un exchange (se verifica contra el exchange antes de guardar). */
  async connect(payload: {
    exchange: ExchangeId
    api_key: string
    api_secret: string
    api_password?: string
    is_testnet?: boolean
    label?: string
  }): Promise<ExchangeConnection> {
    const { data } = await apiClient.post<ExchangeConnection>('/trading/connections/', payload)
    return data
  },

  /** Desconecta el exchange. */
  async disconnect(connectionId: number): Promise<{ id: number; removed: boolean }> {
    const { data } = await apiClient.delete(`/trading/connections/${connectionId}/`)
    return data
  },

  /** Saldos de la conexión. */
  async getBalance(connectionId: number): Promise<BrokerBalance> {
    const { data } = await apiClient.get<BrokerBalance>(`/trading/connections/${connectionId}/balance/`)
    return data
  },

  /** Lanza una orden manual market/limit. */
  async placeOrder(connectionId: number, payload: {
    symbol: string
    side: 'buy' | 'sell'
    type: 'market' | 'limit'
    amount: number
    price?: number
  }): Promise<PlaceOrderResult> {
    const { data } = await apiClient.post<PlaceOrderResult>(
      `/trading/connections/${connectionId}/orders/`, payload,
    )
    return data
  },

  /** Órdenes abiertas de la conexión. */
  async openOrders(connectionId: number, symbol?: string): Promise<BrokerOrder[]> {
    const { data } = await apiClient.get<{ count: number; orders: BrokerOrder[] }>(
      `/trading/connections/${connectionId}/orders/`, { params: symbol ? { symbol } : {} },
    )
    return data.orders
  },

  /** Cancela una orden abierta. */
  async cancelOrder(connectionId: number, orderId: string, symbol: string): Promise<{ id: string; status: string }> {
    const { data } = await apiClient.post(
      `/trading/connections/${connectionId}/orders/cancel/`, { order_id: orderId, symbol },
    )
    return data
  },
}
