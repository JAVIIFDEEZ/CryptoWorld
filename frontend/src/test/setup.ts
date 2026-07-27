/**
 * src/test/setup.ts — Setup global de los tests (Vitest + Testing Library).
 *
 * Carga los matchers de jest-dom y limpia el DOM tras cada test. También
 * stubea matchMedia, que jsdom no implementa, para los hooks que lo usan.
 */

import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}
