/**
 * i18n/index.ts — Internacionalización (react-i18next).
 *
 * Español es el idioma por defecto y de respaldo (la app nació en español, así
 * ninguna clave sin traducir rompe la UI). El idioma elegido se persiste en
 * localStorage y, si no hay elección, se detecta del navegador. La migración de
 * textos es incremental por módulos: los componentes aún sin migrar siguen
 * mostrando su literal en español exactamente igual que antes.
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import es from './locales/es.json'
import en from './locales/en.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
] as const

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      es: { translation: es },
      en: { translation: en },
    },
    fallbackLng: 'es',
    supportedLngs: SUPPORTED_LANGUAGES.map((l) => l.code),
    interpolation: { escapeValue: false }, // React ya escapa
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'cw.lang',
    },
    returnEmptyString: false,
  })

export default i18n
