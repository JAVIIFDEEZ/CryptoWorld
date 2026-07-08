/**
 * components/layout/OnboardingTour.tsx — Tour de bienvenida guiado.
 *
 * Presenta los módulos del sistema en un carrusel de pasos la primera vez que
 * el usuario entra (persistido en localStorage). Re-lanzable desde cualquier
 * sitio despachando el evento window 'cw:onboarding'. No bloquea: se puede
 * cerrar en cualquier paso.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const SEEN_KEY = 'cw.onboarded.v1'

interface Step {
  icon: string
  title: string
  body: string
  to?: string
  cta?: string
}

const STEPS: Step[] = [
  {
    icon: '🚀', title: 'Bienvenido a CryptoWorld',
    body: 'Una plataforma de análisis e inteligencia cripto de grado profesional: análisis técnico, IA, datos on-chain, trading real con controles de riesgo y un motor que fusiona todo. Te enseño lo esencial en 30 segundos.',
  },
  {
    icon: '🎯', title: 'Confluencia 360°',
    body: 'En Análisis Técnico, el motor de confluencia fusiona señal técnica, ML, presión on-chain y noticias en un único veredicto por activo — con pesos que aprenden del acierto real de cada fuente y su propio backtest.',
    to: '/analysis', cta: 'Ver Análisis Técnico',
  },
  {
    icon: '🧬', title: 'Generador de estrategias',
    body: 'Un algoritmo genético evoluciona estrategias nuevas combinando 31 indicadores y las filtra por robustez (walk-forward, PBO, Monte Carlo). El fitness es fuera de muestra; nada de sobreajuste.',
    to: '/strategies', cta: 'Abrir el Generador',
  },
  {
    icon: '⛓', title: 'Inteligencia on-chain',
    body: 'Explora wallets con dossier cruzado, sigue los mayores movimientos de ballenas, mide la presión de flujo a/desde exchanges y vigila direcciones para que te avisen cuando muevan en grande.',
    to: '/blockchain', cta: 'Ir a Blockchain',
  },
  {
    icon: '🛡', title: 'Cartera y riesgo',
    body: 'El módulo de cartera agrega tu exposición real+paper+manual y mide el riesgo del libro completo: VaR/CVaR histórico, stress testing y las barreras del OMS (pérdida diaria y concentración) que protegen tu ejecución real.',
    to: '/portfolio', cta: 'Ver mi Cartera',
  },
  {
    icon: '⌨️', title: 'Un último truco',
    body: 'Pulsa ⌘K (o Ctrl+K) en cualquier momento para la paleta de comandos: navega a cualquier módulo o activo al instante. ¡Listo para empezar!',
  },
]

export default function OnboardingTour() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (!localStorage.getItem(SEEN_KEY)) {
      const t = window.setTimeout(() => setOpen(true), 800)   // deja cargar la app
      return () => window.clearTimeout(t)
    }
  }, [])

  useEffect(() => {
    const relaunch = () => { setStep(0); setOpen(true) }
    window.addEventListener('cw:onboarding', relaunch)
    return () => window.removeEventListener('cw:onboarding', relaunch)
  }, [])

  function finish() {
    localStorage.setItem(SEEN_KEY, '1')
    setOpen(false)
  }

  if (!open) return null
  const s = STEPS[step]
  const last = step === STEPS.length - 1

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-slate-800 border border-slate-600 rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-6 text-center">
          <div className="text-4xl mb-3">{s.icon}</div>
          <h2 className="text-lg font-bold text-white mb-2">{s.title}</h2>
          <p className="text-sm text-slate-400 leading-relaxed">{s.body}</p>
          {s.to && (
            <button
              onClick={() => { finish(); navigate(s.to!) }}
              className="mt-4 text-xs px-3 py-1.5 rounded-lg bg-blue-600/20 text-blue-300 border border-blue-500/30 hover:bg-blue-600/30 transition-colors"
            >
              {s.cta} →
            </button>
          )}
        </div>

        {/* Progreso + navegación */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-700 bg-slate-900/40">
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <span key={i} className={`w-1.5 h-1.5 rounded-full transition-colors ${i === step ? 'bg-blue-400' : 'bg-slate-600'}`} />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={finish} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
              {last ? '' : 'Saltar'}
            </button>
            {step > 0 && (
              <button
                onClick={() => setStep((v) => v - 1)}
                className="text-xs px-3 py-1.5 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
              >
                Atrás
              </button>
            )}
            <button
              onClick={() => (last ? finish() : setStep((v) => v + 1))}
              className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors font-medium"
            >
              {last ? 'Empezar' : 'Siguiente'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
