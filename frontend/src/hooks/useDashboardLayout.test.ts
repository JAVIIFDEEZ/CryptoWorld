/**
 * useDashboardLayout.test.ts — Personalización persistente del dashboard.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useDashboardLayout } from './useDashboardLayout'

beforeEach(() => localStorage.clear())

describe('useDashboardLayout', () => {
  it('starts with all widgets visible in the default order', () => {
    const { result } = renderHook(() => useDashboardLayout())
    expect(result.current.layout.map((w) => w.id)).toEqual(['market', 'catalog', 'watchlist', 'movers'])
    expect(result.current.layout.every((w) => w.visible)).toBe(true)
  })

  it('toggles visibility and persists it', () => {
    const { result, unmount } = renderHook(() => useDashboardLayout())
    act(() => result.current.toggle('catalog'))
    expect(result.current.layout.find((w) => w.id === 'catalog')?.visible).toBe(false)
    unmount()
    const { result: again } = renderHook(() => useDashboardLayout())
    expect(again.current.layout.find((w) => w.id === 'catalog')?.visible).toBe(false)
  })

  it('moves a widget up and down', () => {
    const { result } = renderHook(() => useDashboardLayout())
    act(() => result.current.move('catalog', -1))
    expect(result.current.layout.map((w) => w.id)).toEqual(['catalog', 'market', 'watchlist', 'movers'])
    act(() => result.current.move('catalog', 1))
    expect(result.current.layout.map((w) => w.id)).toEqual(['market', 'catalog', 'watchlist', 'movers'])
  })

  it('does not move past the edges', () => {
    const { result } = renderHook(() => useDashboardLayout())
    act(() => result.current.move('market', -1))
    expect(result.current.layout[0].id).toBe('market')
  })

  it('reset restores the default layout', () => {
    const { result } = renderHook(() => useDashboardLayout())
    act(() => { result.current.toggle('market'); result.current.move('movers', -1) })
    act(() => result.current.reset())
    expect(result.current.layout.map((w) => w.id)).toEqual(['market', 'catalog', 'watchlist', 'movers'])
    expect(result.current.layout.every((w) => w.visible)).toBe(true)
  })

  it('reconciles unknown/missing widgets from stored layout', () => {
    localStorage.setItem('cw.dashboard.layout.v1', JSON.stringify([
      { id: 'movers', visible: false }, { id: 'obsolete', visible: true },
    ]))
    const { result } = renderHook(() => useDashboardLayout())
    const ids = result.current.layout.map((w) => w.id)
    expect(ids).toContain('movers')
    expect(ids).not.toContain('obsolete')          // descartado
    expect(ids).toEqual(expect.arrayContaining(['market', 'catalog', 'watchlist']))  // añadidos
    expect(result.current.layout.find((w) => w.id === 'movers')?.visible).toBe(false) // respeta lo guardado
  })
})
