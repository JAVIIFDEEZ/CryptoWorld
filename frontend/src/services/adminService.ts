/**
 * services/adminService.ts — Servicio HTTP para el panel de administración.
 *
 * Encapsula todas las llamadas a /api/admin/*.
 */

import apiClient from './api'

// ── Tipos ──────────────────────────────────────────────────────────

export interface AdminUser {
  id: number
  email: string
  username: string
  is_active: boolean
  is_staff: boolean
  role: 'user' | 'admin'
  is_email_verified: boolean
  is_2fa_enabled: boolean
  date_joined: string
}

export interface AdminAsset {
  id: number
  symbol: string
  name: string
  current_price: string
  market_cap: string | null
  volume_24h: string | null
  price_change_24h: string | null
  coingecko_id: string | null
  logo_url: string | null
}

export interface AdminStats {
  total_users: number
  active_users: number
  verified_users: number
  users_with_2fa: number
  admin_users: number
  total_assets: number
  total_analyses: number
}

export interface UpdateUserPayload {
  is_active?: boolean
  role?: 'user' | 'admin'
  is_email_verified?: boolean
}

export interface CreateAssetPayload {
  symbol: string
  name: string
  current_price: string
  market_cap?: string
  volume_24h?: string
  price_change_24h?: string
  coingecko_id?: string
  logo_url?: string
}

export interface UpdateAssetPayload {
  name?: string
  current_price?: string
  market_cap?: string
  volume_24h?: string
  price_change_24h?: string
  coingecko_id?: string
  logo_url?: string
}

// ── Servicio ───────────────────────────────────────────────────────

export const adminService = {
  // ── Stats ────────────────────────────────────────────────────────
  async getStats(): Promise<AdminStats> {
    const { data } = await apiClient.get<AdminStats>('/admin/stats/')
    return data
  },

  // ── Users ────────────────────────────────────────────────────────
  async listUsers(): Promise<AdminUser[]> {
    const { data } = await apiClient.get<AdminUser[]>('/admin/users/')
    return data
  },

  async getUser(userId: number): Promise<AdminUser> {
    const { data } = await apiClient.get<AdminUser>(`/admin/users/${userId}/`)
    return data
  },

  async updateUser(userId: number, payload: UpdateUserPayload): Promise<AdminUser> {
    const { data } = await apiClient.patch<AdminUser>(`/admin/users/${userId}/`, payload)
    return data
  },

  async deleteUser(userId: number): Promise<void> {
    await apiClient.delete(`/admin/users/${userId}/`)
  },

  // ── Assets ───────────────────────────────────────────────────────
  async listAssets(): Promise<AdminAsset[]> {
    const { data } = await apiClient.get<AdminAsset[]>('/admin/assets/')
    return data
  },

  async createAsset(payload: CreateAssetPayload): Promise<AdminAsset> {
    const { data } = await apiClient.post<AdminAsset>('/admin/assets/', payload)
    return data
  },

  async updateAsset(assetId: number, payload: UpdateAssetPayload): Promise<AdminAsset> {
    const { data } = await apiClient.patch<AdminAsset>(`/admin/assets/${assetId}/`, payload)
    return data
  },

  async deleteAsset(assetId: number): Promise<void> {
    await apiClient.delete(`/admin/assets/${assetId}/`)
  },
}
