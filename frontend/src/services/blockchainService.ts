/**
 * services/blockchainService.ts — API calls para métricas on-chain.
 *
 * Endpoints:
 *   GET /api/blockchain/metrics/?symbol=BTC&metric=&days=
 *     → Series históricas de BTC (Blockchain.com, solo BTC)
 *
 *   GET /api/blockchain/multichain/?symbol=ETH
 *     → Snapshot de estadísticas actuales multi-chain (Blockchair)
 *     → Chains: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR
 */

import apiClient from './api'

export type OnChainMetric =
  | 'active_addresses'
  | 'hashrate'
  | 'tx_count'
  | 'difficulty'
  | 'mempool_size'
  | 'miners_revenue'
  | 'transaction_fees'
  | 'avg_block_size'

export const METRIC_LABELS: Record<OnChainMetric, string> = {
  active_addresses: 'Direcciones activas',
  hashrate: 'Hash Rate',
  tx_count: 'Transacciones diarias',
  difficulty: 'Dificultad de minería',
  mempool_size: 'Tamaño Mempool',
  miners_revenue: 'Ingresos mineros',
  transaction_fees: 'Fees de transacción',
  avg_block_size: 'Tamaño medio de bloque',
}

export interface MetricPoint {
  timestamp: number
  value: number
}

export interface OnChainMetricsResponse {
  symbol: string
  metric: OnChainMetric
  metric_label: string
  description: string
  timespan: string
  total_points: number
  source: string
  data: MetricPoint[]
  error?: string
}

// ── Multi-chain snapshot (Blockchair) ──────────────────────────────

export const MULTICHAIN_SYMBOLS = ['BTC', 'ETH', 'LTC', 'DOGE', 'BCH', 'XRP', 'ADA', 'DOT', 'XLM', 'XMR'] as const
export type MultiChainSymbol = typeof MULTICHAIN_SYMBOLS[number]

export interface MultiChainStatItem {
  key: string
  label: string
  value: number | string | null
  unit: string
}

export interface MultiChainStatsResponse {
  symbol: string
  source: string
  best_block_time: string | null
  best_block_height: number | null
  supported: string[]
  stats: MultiChainStatItem[]
  error?: string
}

// ── Explorador on-chain de wallets (Blockscout) ────────────────────

export interface WalletChain {
  slug: string
  name: string
  native: string
  chain_id: number
  explorer_url: string
}

export interface WalletToken {
  address: string | null
  name: string
  symbol: string
  balance: number
  price_usd: number | null
  value_usd: number | null
}

export interface WalletTransaction {
  hash: string | null
  method: string | null
  direction: 'in' | 'out' | 'self'
  from: string | null
  to: string | null
  value_native: number
  status: string | null
  timestamp: string | null
}

export interface WalletOverview {
  chain: string
  chain_name: string
  explorer_url: string
  address: string
  ens_name: string | null
  is_contract: boolean
  is_verified: boolean
  native_symbol: string
  native_balance: number
  native_price_usd: number | null
  native_value_usd: number | null
  token_count: number
  tokens_value_usd: number | null
  portfolio_value_usd: number | null
  tokens: WalletToken[]
  transactions: WalletTransaction[]
  source: string
  error?: string
}

// ── Salud de red / rastreador de gas (Blockscout /stats) ───────────

export interface ChainHealth {
  chain: string
  chain_name: string
  native_symbol: string
  explorer_url: string
  gas_slow: number | null
  gas_average: number | null
  gas_fast: number | null
  gas_level: 'cheap' | 'normal' | 'high' | 'unknown'
  gas_text: string
  gas_unit: string
  gas_updated_at: string | null
  network_utilization_pct: number | null
  block_time_sec: number | null
  coin_price_usd: number | null
  coin_price_change_pct: number | null
  total_transactions: string | null
  total_blocks: string | null
  total_addresses: string | null
  transactions_today: string | null
  source: string
  error?: string
}

// ── Historial de saldo (curva de patrimonio on-chain) ──────────────

export interface BalancePoint {
  date: string
  balance: number
  value_usd_at_today_price: number | null
}

export interface WalletBalanceHistory {
  chain: string
  address: string
  native_symbol: string
  price_now_usd: number | null
  points: number
  history: BalancePoint[]
  note: string
  source: string
  error?: string
}

// ── Watchlist de direcciones + alertas ─────────────────────────────

export interface WatchedAddress {
  id: number
  chain: string
  address: string
  label: string | null
  native_symbol: string | null
  alert_threshold_pct: number
  last_balance: number | null
  last_value_usd: number | null
  last_checked_at: string | null
  created_at: string
  error?: string
}

export interface AddressAlert {
  id: number
  watched_id: number
  chain: string
  address: string
  label: string | null
  direction: 'increase' | 'decrease'
  delta: number
  delta_pct: number
  balance_after: number
  value_usd: number | null
  created_at: string
}

export interface WatchlistResponse {
  count: number
  results: WatchedAddress[]
  alerts: AddressAlert[]
}

// ── Mayores movimientos on-chain (whale watch) ─────────────────────

export interface MovementParty {
  address: string | null
  label: string | null
  is_contract: boolean
}

export interface WhaleMovement {
  kind: 'native' | 'token'
  symbol: string
  token_name?: string | null
  amount: number
  value_usd: number | null
  from: MovementParty
  to: MovementParty
  hash: string | null
  method: string | null
  timestamp: string | null
  explorer_url: string | null
}

export interface WhaleMovementsResponse {
  chain: string
  chain_name: string
  native_symbol: string
  min_usd: number
  scanned: number
  count: number
  movements: WhaleMovement[]
  partial?: boolean
  note: string
  source: string
  error?: string
}

// ── Presión on-chain (flujo hacia/desde exchanges) ─────────────────

export interface PressureBucket {
  start_ms: number
  inflow_usd: number
  outflow_usd: number
  pressure: number
  count: number
}

export interface PressureMovement {
  symbol: string
  kind: 'native' | 'token'
  amount: number
  value_usd: number
  direction: 'to_exchange' | 'from_exchange' | 'between_exchanges' | 'unknown'
  from_label: string | null
  to_label: string | null
  tx_hash: string
  moved_at: string
}

export interface OnChainPressure {
  chain: string
  window_hours: number
  bucket_hours: number
  total_movements: number
  inflow_usd: number
  outflow_usd: number
  net_flow_usd: number
  pressure: number
  classified_count: number
  unknown_count: number
  verdict: 'ACUMULACION' | 'PRESION_VENDEDORA' | 'EQUILIBRIO' | 'INSUFICIENTE'
  verdict_text: string
  series: PressureBucket[]
  top_movements: PressureMovement[]
  note: string
  error?: string
}

// ── Radar de dinero inteligente ────────────────────────────────────

export interface SmartMoneyRow {
  address: string
  moves: number
  hit_rate: number
  avg_captured_pct: number
  total_value_usd: number
  last_move_ts: number
}

export interface SmartMoneyRadar {
  chain: string
  window_days: number
  horizon_hours: number
  min_moves: number
  movements_total: number
  movements_evaluated: number
  leaderboard: SmartMoneyRow[]
  note: string
  error?: string
}

export const blockchainService = {
  /** Obtener datos históricos de una métrica on-chain de Bitcoin */
  getMetrics: async (
    metric: OnChainMetric = 'active_addresses',
    days = 30,
  ): Promise<OnChainMetricsResponse> => {
    const params = new URLSearchParams({
      symbol: 'BTC',
      metric,
      days: String(days),
    })
    const { data } = await apiClient.get(`/blockchain/metrics/?${params}`)
    return data
  },

  /** Obtener snapshot de estadísticas actuales para cualquier chain soportada */
  getMultiChainStats: async (symbol: MultiChainSymbol): Promise<MultiChainStatsResponse> => {
    const params = new URLSearchParams({ symbol })
    const { data } = await apiClient.get(`/blockchain/multichain/?${params}`)
    return data
  },

  /** Redes soportadas por el explorador de wallets on-chain (Blockscout). */
  getWalletChains: async (): Promise<WalletChain[]> => {
    const { data } = await apiClient.get<{ chains: WalletChain[] }>('/blockchain/wallet/chains/')
    return data.chains
  },

  /** Retrato on-chain de una dirección: saldo, tokens valorados y transacciones. */
  getWalletOverview: async (chain: string, address: string): Promise<WalletOverview> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/wallet/?${params}`)
    return data
  },

  /** Serie diaria del saldo nativo de una dirección (curva de patrimonio). */
  getWalletBalanceHistory: async (chain: string, address: string): Promise<WalletBalanceHistory> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/wallet/history/?${params}`)
    return data
  },

  /** Salud de red y rastreador de gas de una cadena. */
  getChainHealth: async (chain: string): Promise<ChainHealth> => {
    const params = new URLSearchParams({ chain })
    const { data } = await apiClient.get(`/blockchain/health/?${params}`)
    return data
  },

  /** Radar de dinero inteligente: direcciones que anticiparon el precio. */
  getSmartMoney: async (chain: string, days = 30): Promise<SmartMoneyRadar> => {
    const params = new URLSearchParams({ chain, days: String(days) })
    const { data } = await apiClient.get(`/blockchain/smartmoney/?${params}`)
    return data
  },

  /** Indicador de presión on-chain: depósitos vs retiradas de exchanges. */
  getOnChainPressure: async (chain: string, hours = 24): Promise<OnChainPressure> => {
    const params = new URLSearchParams({ chain, hours: String(hours) })
    const { data } = await apiClient.get(`/blockchain/pressure/?${params}`)
    return data
  },

  /** Mayores movimientos on-chain recientes (nativos + tokens) por valor en USD. */
  getWhaleMovements: async (chain: string, minUsd = 100000, limit = 25): Promise<WhaleMovementsResponse> => {
    const params = new URLSearchParams({ chain, min_usd: String(minUsd), limit: String(limit) })
    const { data } = await apiClient.get(`/blockchain/movements/?${params}`)
    return data
  },

  /** Watchlist de direcciones on-chain del usuario con sus alertas. */
  getWatchlist: async (): Promise<WatchlistResponse> => {
    const { data } = await apiClient.get('/blockchain/watchlist/')
    return data
  },

  /** Añade una dirección a la watchlist. */
  addWatchedAddress: async (
    chain: string, address: string, label?: string, thresholdPct?: number,
  ): Promise<WatchedAddress> => {
    const { data } = await apiClient.post('/blockchain/watchlist/', {
      chain, address,
      ...(label ? { label } : {}),
      ...(thresholdPct != null ? { threshold_pct: thresholdPct } : {}),
    })
    return data
  },

  /** Elimina una dirección vigilada. */
  removeWatchedAddress: async (id: number): Promise<{ id: number; removed: boolean }> => {
    const { data } = await apiClient.delete(`/blockchain/watchlist/${id}/`)
    return data
  },

  // ── Forense on-chain ─────────────────────────────────────────────

  /** Árbol de flujo saliente de una dirección (sigue el dinero). */
  traceFlow: async (chain: string, address: string, depth = 2): Promise<FlowTrace> => {
    const params = new URLSearchParams({ chain, address, depth: String(depth) })
    const { data } = await apiClient.get(`/blockchain/forensics/flow/?${params}`)
    return data
  },

  /** Radiografía de concentración de tenedores de un token. */
  tokenConcentration: async (chain: string, token: string): Promise<TokenConcentration> => {
    const params = new URLSearchParams({ chain, token })
    const { data } = await apiClient.get(`/blockchain/forensics/concentration/?${params}`)
    return data
  },

  /** Huella conductual de una dirección (heatmap, arquetipo). */
  walletFingerprint: async (chain: string, address: string): Promise<WalletFingerprint> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/forensics/fingerprint/?${params}`)
    return data
  },

  /** Puntuación de riesgo 0-100 de una dirección. */
  addressRisk: async (chain: string, address: string): Promise<AddressRisk> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/forensics/risk/?${params}`)
    return data
  },

  /** Aprobaciones ERC-20 vivas de una dirección y su peligrosidad. */
  approvals: async (chain: string, address: string): Promise<ApprovalsResult> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/forensics/approvals/?${params}`)
    return data
  },

  /** Grafo de entidad: direcciones que se mueven junto a la raíz. */
  entityGraph: async (chain: string, address: string): Promise<EntityGraph> => {
    const params = new URLSearchParams({ chain, address })
    const { data } = await apiClient.get(`/blockchain/forensics/entity/?${params}`)
    return data
  },

  /** Due diligence de un token: riesgo de rug/honeypot a nivel de contrato. */
  tokenSafety: async (chain: string, token: string): Promise<TokenSafety> => {
    const params = new URLSearchParams({ chain, token })
    const { data } = await apiClient.get(`/blockchain/forensics/token-safety/?${params}`)
    return data
  },
}

// ── Tipos de seguridad de token ────────────────────────────────────

export interface SafetyFlag {
  category: string
  weight: number
  label: string
  detail: string
  source?: string
}

export interface TokenSafety {
  status?: 'OK'
  error?: string
  chain: string
  token: string
  token_name: string | null
  token_symbol: string | null
  score: number
  verdict: 'PELIGROSO' | 'RIESGO ALTO' | 'PRECAUCIÓN' | 'RAZONABLE'
  verified: boolean
  ownership_renounced: boolean
  is_proxy: boolean
  owner: string | null
  flags: SafetyFlag[]
  green_flags: string[]
  top10_concentration_pct: number | null
  note: string
}

// ── Tipos de riesgo / aprobaciones / entidad ───────────────────────

export interface RiskFactor {
  kind: string
  category: string
  weight: number
  detail: string
}

export interface AddressRisk {
  status?: 'OK'
  error?: string
  chain: string
  address: string
  score: number
  band: 'SEVERO' | 'ALTO' | 'MEDIO' | 'BAJO'
  factors: RiskFactor[]
  flagged_counterparties: number
  counterparties_analyzed?: number
  self_labels?: string[]
  note: string
}

export interface Approval {
  token: string
  token_symbol: string
  spender: string
  spender_label: string | null
  spender_verified: boolean
  is_unlimited: boolean
  amount: number | null
  risk: 'SEVERO' | 'ALTO' | 'MEDIO' | 'BAJO'
  reason: string
}

export interface ApprovalsResult {
  status?: 'OK'
  error?: string
  chain: string
  address: string
  approvals: Approval[]
  total: number
  unlimited: number
  counts: Record<string, number>
  worst: string
  note: string
}

export interface EntityNode {
  address: string
  degree: number
  strength: number
  in_entity: boolean
  is_root: boolean
}

export interface EntityGraph {
  status?: 'OK'
  error?: string
  chain: string
  root: string
  nodes: EntityNode[]
  edges: { a: string; b: string; weight: number }[]
  entity: string[]
  entity_size: number
  components: number
  neighbors_scanned?: number
  note: string
}

// ── Tipos del submódulo forense ────────────────────────────────────

export interface FlowNode {
  address: string
  level: number
  value_in?: number
  tx_count?: number
  share?: number
  revisited?: boolean
  fan_out: number
  total_out: number
  children: FlowNode[]
}

export interface FlowPattern {
  type: 'fan_out' | 'peel_chain'
  address: string
  counterparties?: number
  depth?: number
  note: string
}

export interface FlowTrace {
  status?: 'OK'
  error?: string
  chain: string
  address: string
  depth: number
  nodes_fetched: number
  tree: FlowNode
  patterns: FlowPattern[]
  note?: string
}

export interface ConcentrationTopHolder {
  address: string
  value: number
  share_pct: number
  is_contract: boolean
}

export interface TokenConcentration {
  status?: 'OK'
  error?: string
  chain: string
  token: string
  token_name: string | null
  token_symbol: string | null
  concentration: {
    available: boolean
    sample_size?: number
    holders_count_total?: number | null
    top10_share_pct?: number
    top50_share_pct?: number
    gini?: number | null
    hhi?: number
    contract_share_pct?: number
    top_holders?: ConcentrationTopHolder[]
    verdict?: 'CRÍTICA' | 'ALTA' | 'MODERADA' | 'DISTRIBUIDA'
    verdict_note?: string
    note?: string
  }
}

export interface WalletFingerprint {
  status?: 'OK'
  error?: string
  chain: string
  address: string
  fingerprint: {
    available: boolean
    sample_txs?: number
    span_days?: number
    days_since_last?: number
    txs_per_week?: number
    in_count?: number
    out_count?: number
    unique_counterparties?: number
    diversity?: number
    median_gap_hours?: number | null
    burstiness?: number | null
    heatmap?: number[][]
    archetype?: string
    traits?: string[]
    note?: string
  }
}
