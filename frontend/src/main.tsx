/**
 * main.tsx — Punto de entrada de la aplicación React.
 *
 * Responsabilidad: arrancar la SPA, montar el árbol de componentes
 * dentro del div#root del index.html e importar los estilos globales.
 *
 * StrictMode activa advertencias adicionales durante desarrollo.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './i18n' // inicializa la internacionalización antes de montar la app

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// PWA: registra el service worker solo en producción (no interfiere en desarrollo).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* sin PWA */ })
  })
}
