/**
 * strategyGeneratorService.test.ts — Contrato del servicio del generador.
 *
 * Verifica que cada método llama al endpoint correcto con el payload esperado y
 * mapea bien la respuesta, con el cliente axios mockeado.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import apiClient from '@/services/api'
import {
  strategyGeneratorService,
  isGenerationReport,
  isSpecRobustnessReport,
} from './strategyGeneratorService'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

const mockApi = apiClient as unknown as { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }

beforeEach(() => {
  mockApi.get.mockReset()
  mockApi.post.mockReset()
})

describe('strategyGeneratorService', () => {
  it('launch posts to the generate endpoint and returns the job', async () => {
    mockApi.post.mockResolvedValue({ data: { job_id: 'j1', status: 'PENDING', poll_url: '/x' } })
    const r = await strategyGeneratorService.launch({ asset_symbol: 'BTC', preset: 'fast' })
    expect(mockApi.post).toHaveBeenCalledWith('/strategies/generate/', { asset_symbol: 'BTC', preset: 'fast' })
    expect(r.job_id).toBe('j1')
  })

  it('getStatus polls the job by id', async () => {
    mockApi.get.mockResolvedValue({ data: { job_id: 'j1', status: 'SUCCESS' } })
    const r = await strategyGeneratorService.getStatus('j1')
    expect(mockApi.get).toHaveBeenCalledWith('/strategies/generate/j1/')
    expect(r.status).toBe('SUCCESS')
  })

  it('listSaved unwraps results and forwards filters', async () => {
    mockApi.get.mockResolvedValue({ data: { count: 1, results: [{ id: 7 }] } })
    const r = await strategyGeneratorService.listSaved({ asset_symbol: 'ETH', limit: 5 })
    expect(mockApi.get).toHaveBeenCalledWith('/strategies/', { params: { asset_symbol: 'ETH', limit: 5 } })
    expect(r).toHaveLength(1)
    expect(r[0].id).toBe(7)
  })

  it('launchRobustness posts the spec to the deep-dive endpoint', async () => {
    mockApi.post.mockResolvedValue({ data: { job_id: 'r1', status: 'PENDING', poll_url: '/y' } })
    await strategyGeneratorService.launchRobustness({ asset_symbol: 'BTC', strategy_id: 3, preset: 'fast' })
    expect(mockApi.post).toHaveBeenCalledWith('/strategies/robustness/', { asset_symbol: 'BTC', strategy_id: 3, preset: 'fast' })
  })

  it('setMonitor posts the active flag', async () => {
    mockApi.post.mockResolvedValue({ data: { strategy_id: 9, is_monitored: true } })
    const r = await strategyGeneratorService.setMonitor(9, true)
    expect(mockApi.post).toHaveBeenCalledWith('/strategies/9/monitor/', { active: true })
    expect(r.is_monitored).toBe(true)
  })

  it('getSignal hits the signal endpoint', async () => {
    mockApi.get.mockResolvedValue({ data: { strategy_id: 9, signal: 'BUY' } })
    const r = await strategyGeneratorService.getSignal(9)
    expect(mockApi.get).toHaveBeenCalledWith('/strategies/9/signal/')
    expect(r.signal).toBe('BUY')
  })

  it('listSignalEvents unwraps the recent feed', async () => {
    mockApi.get.mockResolvedValue({ data: { count: 2, results: [{ id: 1 }, { id: 2 }] } })
    const r = await strategyGeneratorService.listSignalEvents(10)
    expect(mockApi.get).toHaveBeenCalledWith('/strategies/signals/recent/', { params: { limit: 10 } })
    expect(r).toHaveLength(2)
  })
})

describe('type guards', () => {
  it('isGenerationReport detects a ranking report', () => {
    expect(isGenerationReport({ ranking: [] } as never)).toBe(true)
    expect(isGenerationReport({ error: 'x' })).toBe(false)
    expect(isGenerationReport(undefined)).toBe(false)
  })

  it('isSpecRobustnessReport detects a robustness report', () => {
    expect(isSpecRobustnessReport({ robustness_score: 70 } as never)).toBe(true)
    expect(isSpecRobustnessReport({ error: 'x' })).toBe(false)
    expect(isSpecRobustnessReport(undefined)).toBe(false)
  })
})
