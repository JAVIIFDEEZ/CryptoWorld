/**
 * components/ErrorBoundary.tsx — Captura de errores de render de React.
 *
 * Evita la "pantalla en blanco": si cualquier componente hijo lanza una
 * excepción durante el render, se muestra una pantalla de recuperación con
 * la opción de recargar, en lugar de romper toda la aplicación.
 *
 * Los error boundaries deben ser componentes de clase (no hay equivalente
 * con hooks para `componentDidCatch`).
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Registro para depuración; en producción podría enviarse a un servicio.
    console.error('[ErrorBoundary] error de render no controlado:', error, info)
  }

  private handleReload = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 p-6">
        <div className="max-w-md w-full text-center bg-slate-800 border border-slate-700 rounded-xl p-8">
          <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center text-red-400">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
          </div>
          <h1 className="text-lg font-semibold text-white">Algo ha salido mal</h1>
          <p className="text-sm text-slate-400 mt-2">
            Se ha producido un error inesperado en la interfaz. Puedes recargar la página
            para continuar.
          </p>
          {this.state.error?.message && (
            <p className="mt-3 text-xs font-mono text-slate-500 break-words bg-slate-900/60 rounded-lg px-3 py-2">
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={this.handleReload}
            className="mt-5 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Recargar
          </button>
        </div>
      </div>
    )
  }
}
