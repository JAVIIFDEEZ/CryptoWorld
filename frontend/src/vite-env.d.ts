/// <reference types="vite/client" />

/**
 * vite-env.d.ts — Declaraciones de tipos para variables de entorno de Vite.
 *
 * La directiva <reference types="vite/client" /> añade los tipos de:
 *   - import.meta.env  (VITE_* variables de entorno)
 *   - import.meta.hot  (HMR API)
 *   - importaciones de assets (PNG, SVG, etc.)
 *
 * Sin este archivo TypeScript no reconoce import.meta.env y falla el build.
 */

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
