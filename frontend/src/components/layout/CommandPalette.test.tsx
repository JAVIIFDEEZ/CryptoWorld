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
import CommandPalette, { coincide, normalizar } from './CommandPalette'
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

  it('encuentra una sección por lo que uno quiere hacer, no por su nombre', async () => {
    // Nadie busca «Mercado» cuando quiere ver si sus correlaciones se han movido.
    // Sin alias, una funcionalidad que existe es una que no se encuentra.
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    open()
    const input = await screen.findByPlaceholderText(/Buscar secciones/)
    fireEvent.change(input, { target: { value: 'correlaciones' } })
    expect(screen.getByText('Mercado')).toBeInTheDocument()
  })

  it('busca sin acentos', async () => {
    // «metodologia» tiene que encontrar «Metodología»: quien escribe rápido o sin
    // tildes no puede quedarse sin acceso a media aplicación.
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    open()
    const input = await screen.findByPlaceholderText(/Buscar secciones/)
    fireEvent.change(input, { target: { value: 'metodologia' } })
    expect(screen.getByText('Metodología')).toBeInTheDocument()
  })

  it('lista las secciones que faltaban', async () => {
    // Metodología y Trading existen como rutas y no estaban en la paleta, así que
    // solo se llegaba a ellas por el menú.
    render(<MemoryRouter><CommandPalette /></MemoryRouter>)
    open()
    await screen.findByPlaceholderText(/Buscar secciones/)
    expect(screen.getByText('Metodología')).toBeInTheDocument()
    expect(screen.getByText('Trading')).toBeInTheDocument()
  })
})

describe('coincide', () => {
  const item = {
    id: 'x', label: 'Mercado', path: '/market', group: 'Secciones' as const,
    sublabel: 'Cotizaciones', keywords: ['mapa de calor', 'régimen'],
  }

  it('coincide por nombre, subtítulo y alias', () => {
    expect(coincide(item, 'merc')).toBe(true)
    expect(coincide(item, 'cotiza')).toBe(true)
    expect(coincide(item, 'calor')).toBe(true)
  })

  it('ignora los acentos en los dos lados', () => {
    expect(coincide(item, 'regimen')).toBe(true)
    expect(coincide({ ...item, label: 'Metodología' }, 'metodologia')).toBe(true)
  })

  it('una consulta vacía no filtra nada', () => {
    expect(coincide(item, '   ')).toBe(true)
  })

  it('no inventa coincidencias', () => {
    expect(coincide(item, 'blockchain')).toBe(false)
  })

  it('un destino sin alias sigue funcionando', () => {
    const simple = { id: 'y', label: 'Alertas', path: '/alerts', group: 'Secciones' as const }
    expect(coincide(simple, 'aler')).toBe(true)
    expect(coincide(simple, 'calor')).toBe(false)
  })
})

describe('normalizar', () => {
  it('quita acentos y mayúsculas', () => {
    expect(normalizar('Metodología')).toBe('metodologia')
    expect(normalizar('  RÉGIMEN  ')).toBe('regimen')
  })
})
