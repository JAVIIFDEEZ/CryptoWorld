/**
 * useTheme.test.tsx — Tema claro / oscuro / sistema.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { ThemeProvider, useTheme } from './useTheme'

function wrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove('theme-light')
  // matchMedia por defecto: el sistema prefiere oscuro
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: q.includes('dark'), media: q, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
  }))
})

describe('useTheme', () => {
  it('defaults to dark (no theme-light class)', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('dark')
    expect(result.current.resolved).toBe('dark')
    expect(document.documentElement.classList.contains('theme-light')).toBe(false)
  })

  it('applies the light class and persists when set to light', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => result.current.setTheme('light'))
    expect(result.current.resolved).toBe('light')
    expect(document.documentElement.classList.contains('theme-light')).toBe(true)
    expect(localStorage.getItem('cw.theme')).toBe('light')
  })

  it('resolves system to the OS preference (dark here)', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => result.current.setTheme('system'))
    expect(result.current.resolved).toBe('dark')
    expect(document.documentElement.classList.contains('theme-light')).toBe(false)
  })
})
