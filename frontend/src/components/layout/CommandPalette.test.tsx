/**
 * CommandPalette.test.tsx — Paleta de comandos global.
 *
 * Verifica que se abre con el evento 'open-command-palette', lista las secciones
 * y filtra por la consulta. El servicio de activos se mockea.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act } from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CommandPalette from './CommandPalette'
import { analysisService } from '@/services/analysisService'

vi.mock('@/services/analysisService', async (orig) => {
  const actual = await orig<typeof import('@/services/analysisService')>()
  return { ...actual, analysisService: { ...actual.analysisService, getAssets: vi.fn() } }
})

function open() {
  act(() => { window.dispatchEvent(new Event('open-command-palette')) })
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(analysisService.getAssets).mockResolvedValue([])
  })

  it('is hidden until opened, then shows sections', async () => {
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    expect(screen.queryByPlaceholderText(/Buscar secciones/)).not.toBeInTheDocument()
    open()
    await waitFor(() => expect(screen.getByPlaceholderText(/Buscar secciones/)).toBeInTheDocument())
    expect(screen.getByText('Blockchain')).toBeInTheDocument()
    expect(screen.getByText('Portfolio')).toBeInTheDocument()
  })

  it('filters sections by query', async () => {
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    open()
    const input = await screen.findByPlaceholderText(/Buscar secciones/)
    fireEvent.change(input, { target: { value: 'block' } })
    expect(screen.getByText('Blockchain')).toBeInTheDocument()
    expect(screen.queryByText('Portfolio')).not.toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    open()
    const input = await screen.findByPlaceholderText(/Buscar secciones/)
    fireEvent.change(input, { target: { value: 'zzzznotfound' } })
    expect(screen.getByText(/Sin resultados/)).toBeInTheDocument()
  })
})
