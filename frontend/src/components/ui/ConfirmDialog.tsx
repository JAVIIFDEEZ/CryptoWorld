/**
 * components/ui/ConfirmDialog.tsx — Modal de confirmación reutilizable.
 *
 * Sustituye a window.confirm() por un diálogo consistente con el diseño
 * de la app. Soporta variante destructiva (botón rojo) y estado de carga
 * mientras se ejecuta la acción confirmada.
 */

import type { ReactNode } from 'react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** 'danger' para acciones destructivas (bloquear, revocar...). */
  tone?: 'primary' | 'danger'
  isLoading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  tone = 'primary',
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  const confirmClasses =
    tone === 'danger'
      ? 'bg-red-600 hover:bg-red-700 disabled:bg-red-800'
      : 'bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full shadow-2xl">
        <h3 id="confirm-dialog-title" className="text-xl font-bold text-white mb-3">
          {title}
        </h3>
        <div className="text-slate-300 text-sm mb-6">{description}</div>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 py-2 rounded-lg text-white transition-colors ${confirmClasses}`}
          >
            {isLoading ? 'Procesando...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
