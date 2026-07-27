/**
 * NotificationBell.test.tsx — Campana de notificaciones.
 *
 * Verifica el badge de no leídas, que el panel lista el feed al abrir y que
 * abrir marca como leídas (limpia el badge). El servicio se mockea.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import NotificationBell from './NotificationBell'
import { notificationsService, type NotificationsFeed } from '@/services/notificationsService'

vi.mock('@/services/notificationsService', () => ({
  notificationsService: { getNotifications: vi.fn(), markSeen: vi.fn() },
}))

const FEED: NotificationsFeed = {
  unread: 2,
  count: 2,
  items: [
    { id: 'signal-1', kind: 'signal', title: 'Señal de COMPRA · BTC', body: 'RSI reversal', link: '/strategies', unread: true, created_at: '2026-06-25T10:00:00Z' },
    { id: 'whale-1', kind: 'whale', title: 'Movimiento (entrada) +30.0%', body: '0xabc · ethereum', link: '/blockchain', unread: true, created_at: '2026-06-25T09:00:00Z' },
  ],
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(notificationsService.getNotifications).mockResolvedValue(FEED)
    vi.mocked(notificationsService.markSeen).mockResolvedValue({ unread: 0, seen_at: 'x' })
  })

  it('shows the unread badge from the feed', async () => {
    render(<MemoryRouter><NotificationBell /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
  })

  it('opens the panel listing items and marks as seen', async () => {
    render(<MemoryRouter><NotificationBell /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Notificaciones'))
    await waitFor(() => expect(screen.getByText('Señal de COMPRA · BTC')).toBeInTheDocument())
    expect(screen.getByText(/Movimiento \(entrada\)/)).toBeInTheDocument()
    await waitFor(() => expect(notificationsService.markSeen).toHaveBeenCalled())
    // El badge desaparece tras marcar como leídas
    await waitFor(() => expect(screen.queryByText('2')).not.toBeInTheDocument())
  })

  it('shows an empty state when there are no notifications', async () => {
    vi.mocked(notificationsService.getNotifications).mockResolvedValue({ unread: 0, count: 0, items: [] })
    render(<MemoryRouter><NotificationBell /></MemoryRouter>)
    fireEvent.click(await screen.findByLabelText('Notificaciones'))
    await waitFor(() => expect(screen.getByText(/No tienes notificaciones/)).toBeInTheDocument())
  })
})
