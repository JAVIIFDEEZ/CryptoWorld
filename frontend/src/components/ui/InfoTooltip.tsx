/**
 * components/ui/InfoTooltip.tsx — Icono de ayuda con tooltip al hover.
 *
 * Muestra una breve explicación (1 frase) sobre un término técnico
 * sin ocupar espacio permanente. Pensado para indicadores, métricas
 * y cualquier jerga que un usuario menos avanzado pueda no conocer.
 *
 * El tooltip se abre hacia arriba y es solo informativo
 * (pointer-events-none), por lo que no interfiere con clics.
 */

interface InfoTooltipProps {
  text: string
  className?: string
}

export default function InfoTooltip({ text, className = '' }: InfoTooltipProps) {
  return (
    <span className={`group relative inline-flex items-center align-middle ${className}`}>
      <span
        className="flex items-center justify-center w-3.5 h-3.5 rounded-full border border-slate-600 text-slate-500 text-[9px] font-bold cursor-help hover:border-slate-400 hover:text-slate-300 transition-colors"
        aria-label={text}
        role="img"
      >
        i
      </span>
      <span
        className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-52 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-[11px] leading-snug text-slate-200 opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 z-50 text-left normal-case"
        role="tooltip"
      >
        {text}
      </span>
    </span>
  )
}
