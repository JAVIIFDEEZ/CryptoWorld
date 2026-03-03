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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
