/**
 * i18n.test.ts — Configuración de internacionalización.
 *
 * Verifica que ambos idiomas resuelven las claves, que el cambio de idioma es
 * efectivo, que el español actúa de respaldo y que los catálogos ES/EN tienen
 * exactamente las mismas claves (ninguna traducción olvidada).
 */

import { describe, it, expect } from 'vitest'
import i18n from './index'
import es from './locales/es.json'
import en from './locales/en.json'

function flatKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null
      ? flatKeys(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  )
}

describe('i18n', () => {
  it('resolves keys in Spanish (default) and English', async () => {
    await i18n.changeLanguage('es')
    expect(i18n.t('nav.market')).toBe('Mercado')
    await i18n.changeLanguage('en')
    expect(i18n.t('nav.market')).toBe('Market')
    await i18n.changeLanguage('es')
  })

  it('falls back to Spanish for unsupported languages', async () => {
    await i18n.changeLanguage('fr')
    expect(i18n.t('nav.logout')).toBe('Cerrar sesión')
    await i18n.changeLanguage('es')
  })

  it('ES and EN catalogs have exactly the same keys', () => {
    const esKeys = flatKeys(es).sort()
    const enKeys = flatKeys(en).sort()
    expect(enKeys).toEqual(esKeys)
  })

  it('no catalog value is empty', () => {
    const check = (obj: Record<string, unknown>) => {
      for (const v of Object.values(obj)) {
        if (typeof v === 'object' && v !== null) check(v as Record<string, unknown>)
        else expect(String(v).trim().length).toBeGreaterThan(0)
      }
    }
    check(es); check(en)
  })
})
