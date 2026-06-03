/**
 * components/ui/EmptyState.tsx — Estado vacío reutilizable y consistente.
 *
 * Unifica la apariencia de los "no hay datos" repartidos por la app:
 * icono opcional dentro de un círculo, título, descripción y acción
 * opcional. Por defecto se renderiza como tarjeta (`bg-slate-800`); con
 * `variant="plain"` se usa sin fondo, para incrustarlo dentro de otro panel.
 */

import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  variant?: 'card' | 'plain'
  className?: string
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  variant = 'card',
  className = '',
}: EmptyStateProps) {
  const base =
    variant === 'card'
      ? 'bg-slate-800 rounded-xl border border-slate-700 p-10'
      : 'py-10'
  return (
    <div className={`text-center ${base} ${className}`}>
      {icon && (
        <div className="mx-auto mb-3 w-12 h-12 rounded-full bg-slate-700/50 flex items-center justify-center text-slate-400">
          {icon}
        </div>
      )}
      <p className="text-slate-300 font-medium">{title}</p>
      {description && <p className="text-slate-500 text-sm mt-1 max-w-sm mx-auto">{description}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}
