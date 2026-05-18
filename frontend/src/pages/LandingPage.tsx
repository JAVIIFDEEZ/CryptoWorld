/**
 * pages/LandingPage.tsx — Página de inicio pública de CryptoWorld.
 *
 * Estructura:
 *   1. Navbar fijo con logo + botones Login/Register
 *   2. Hero con orbes animados, headline y CTAs
 *   3. Ticker de precios en tiempo real
 *   4. Stats animadas (indicadores, activos, velas...)
 *   5. Grid de 6 funcionalidades clave
 *   6. Stack tecnológico
 *   7. CTA final
 *   8. Footer
 *
 * Si el usuario ya está autenticado, redirige a /dashboard.
 */

import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { marketService } from '@/services/marketService'

// ── Tipos ──────────────────────────────────────────────────────────

interface TickerItem {
  symbol: string
  price: number
  change: number
}

// ── Datos estáticos ────────────────────────────────────────────────

const STATIC_TICKERS: TickerItem[] = [
  { symbol: 'BTC', price: 67420, change: 2.31 },
  { symbol: 'ETH', price: 3124, change: 1.84 },
  { symbol: 'BNB', price: 412, change: -0.52 },
  { symbol: 'SOL', price: 178, change: 4.17 },
  { symbol: 'XRP', price: 0.62, change: -1.08 },
  { symbol: 'ADA', price: 0.45, change: 0.93 },
  { symbol: 'AVAX', price: 38, change: 3.21 },
  { symbol: 'DOGE', price: 0.158, change: 5.44 },
  { symbol: 'DOT', price: 7.2, change: -0.78 },
  { symbol: 'LINK', price: 14.3, change: 2.05 },
]

// ── Feature icon components ───────────────────────────────────────

const IconTrendingUp = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" />
  </svg>
)
const IconBacktest = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 .49-3.5" />
  </svg>
)
const IconBriefcase = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" /><line x1="12" y1="12" x2="12" y2="17" /><line x1="9" y1="14.5" x2="15" y2="14.5" />
  </svg>
)
const IconChain = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
)
const IconBell = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
)
const IconNewspaper = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2" />
    <path d="M18 14h-8M15 18h-5M10 6h8v4h-8V6z" />
  </svg>
)

const FEATURES = [
  {
    icon: <IconTrendingUp />,
    title: 'Análisis Técnico',
    desc: 'RSI, MACD, Bollinger Bands, EMA, SMA y más de 10 indicadores calculados sobre datos reales de Binance.',
    colorFrom: 'from-blue-500/20',
    colorTo: 'to-cyan-500/20',
    border: 'border-blue-500/30',
    glow: 'hover:shadow-blue-500/20',
    iconBg: 'bg-blue-500/20 text-blue-300',
  },
  {
    icon: <IconBacktest />,
    title: 'Backtesting',
    desc: 'Prueba tus estrategias sobre histórico de 1000 velas (~2.7 años en 1d). Métricas de Sharpe, drawdown y PnL.',
    colorFrom: 'from-purple-500/20',
    colorTo: 'to-pink-500/20',
    border: 'border-purple-500/30',
    glow: 'hover:shadow-purple-500/20',
    iconBg: 'bg-purple-500/20 text-purple-300',
  },
  {
    icon: <IconBriefcase />,
    title: 'Portfolio LONG/SHORT',
    desc: 'Gestión de posiciones con precio medio ponderado AVCO, cierre parcial y seguimiento de PnL en tiempo real.',
    colorFrom: 'from-green-500/20',
    colorTo: 'to-emerald-500/20',
    border: 'border-green-500/30',
    glow: 'hover:shadow-green-500/20',
    iconBg: 'bg-green-500/20 text-green-300',
  },
  {
    icon: <IconChain />,
    title: 'Datos Blockchain',
    desc: 'Monitoriza bloques, transacciones y estado de la red Bitcoin y Ethereum directamente on-chain.',
    colorFrom: 'from-orange-500/20',
    colorTo: 'to-yellow-500/20',
    border: 'border-orange-500/30',
    glow: 'hover:shadow-orange-500/20',
    iconBg: 'bg-orange-500/20 text-orange-300',
  },
  {
    icon: <IconBell />,
    title: 'Alertas de Precio',
    desc: 'Configura alertas de precio personalizadas y recibe notificaciones cuando el mercado alcance tu objetivo.',
    colorFrom: 'from-red-500/20',
    colorTo: 'to-rose-500/20',
    border: 'border-red-500/30',
    glow: 'hover:shadow-red-500/20',
    iconBg: 'bg-red-500/20 text-red-300',
  },
  {
    icon: <IconNewspaper />,
    title: 'Noticias Cripto',
    desc: 'Últimas noticias del mercado cripto agregadas de las principales fuentes mundiales y en tiempo real.',
    colorFrom: 'from-sky-500/20',
    colorTo: 'to-indigo-500/20',
    border: 'border-sky-500/30',
    glow: 'hover:shadow-sky-500/20',
    iconBg: 'bg-sky-500/20 text-sky-300',
  },
]

const TECH_STACK = ['Django REST', 'React 18', 'TypeScript', 'PostgreSQL', 'Redis', 'Celery', 'Binance API', 'Docker', 'JWT + 2FA']

// ── Componentes auxiliares ─────────────────────────────────────────

function AnimatedStat({ end, suffix, label }: Readonly<{ end: number; suffix: string; label: string }>) {
  const [val, setVal] = useState(0)

  useEffect(() => {
    let frame = 0
    const total = 60
    const timer = setInterval(() => {
      frame++
      setVal(Math.round((frame / total) * end))
      if (frame >= total) clearInterval(timer)
    }, 20)
    return () => clearInterval(timer)
  }, [end])

  return (
    <div className="text-center px-6">
      <p className="text-4xl lg:text-5xl font-black text-white tabular-nums">
        {val.toLocaleString()}
        <span className="text-blue-400">{suffix}</span>
      </p>
      <p className="text-slate-400 text-sm mt-2 leading-snug">{label}</p>
    </div>
  )
}

// Icono SVG del logo (rayo)
function LogoIcon({ size = 20 }: Readonly<{ size?: number }>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  )
}

// ── Helpers ───────────────────────────────────────────────────────

function getFearLabel(val: number | null): string | null {
  if (val == null) return null
  if (val >= 75) return 'Codicia extrema'
  if (val >= 55) return 'Codicia'
  if (val >= 45) return 'Neutral'
  if (val >= 25) return 'Miedo'
  return 'Miedo extremo'
}

function getFearColor(val: number | null): string {
  if (val == null) return ''
  if (val >= 55) return 'text-green-400'
  if (val >= 45) return 'text-yellow-400'
  return 'text-red-400'
}

// ── Página ─────────────────────────────────────────────────────────

export default function LandingPage() {
  const { isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const tickers = STATIC_TICKERS
  const [marketCap, setMarketCap] = useState<string | null>(null)
  const [fearGreed, setFearGreed] = useState<number | null>(null)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true })
      return
    }
    // Intentar obtener datos reales del mercado
    marketService.getMarketOverview().then(data => {
      const cap = Number.parseFloat(data.total_market_cap_usd)
      if (!Number.isNaN(cap)) {
        setMarketCap(`$${(cap / 1e12).toFixed(2)}T`)
      }
      if (data.fear_greed_index != null) {
        setFearGreed(data.fear_greed_index)
      }
    }).catch(() => { /* usar defaults */ })
  }, [isAuthenticated, navigate])

  const fearLabel = getFearLabel(fearGreed)
  const fearColor = getFearColor(fearGreed)

  return (
    <div className="min-h-screen bg-[#070b14] text-white overflow-x-hidden">

      {/* ── Fondo animado ── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        {/* Orbes de color */}
        <div className="absolute -top-32 -left-32 w-[500px] h-[500px] bg-blue-600/[0.12] rounded-full blur-3xl animate-pulse" />
        <div
          className="absolute top-1/2 -right-24 w-[400px] h-[400px] bg-purple-600/[0.10] rounded-full blur-3xl animate-pulse"
          style={{ animationDelay: '1.5s' }}
        />
        <div
          className="absolute bottom-0 left-1/4 w-[350px] h-[350px] bg-cyan-600/[0.08] rounded-full blur-3xl animate-pulse"
          style={{ animationDelay: '3s' }}
        />
        {/* Rejilla sutil */}
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(148,163,184,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.5) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
      </div>

      {/* ════════════════════════════════════════
          NAVBAR
      ════════════════════════════════════════ */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 lg:px-16 py-4 bg-[#070b14]/80 backdrop-blur-xl border-b border-white/[0.06]">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white">
            <LogoIcon size={16} />
          </div>
          <span className="font-bold text-[17px] tracking-tight">
            Crypto<span className="text-blue-400">World</span>
          </span>
        </div>

        {/* Acciones */}
        <div className="flex items-center gap-2">
          <Link
            to="/login"
            className="hidden sm:block text-slate-300 hover:text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-white/5 transition-all"
          >
            Iniciar sesión
          </Link>
          <Link
            to="/register"
            className="bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all hover:shadow-lg hover:shadow-blue-500/25"
          >
            Crear cuenta
          </Link>
        </div>
      </nav>

      {/* ════════════════════════════════════════
          HERO
      ════════════════════════════════════════ */}
      <section className="relative z-10 min-h-screen flex flex-col items-center justify-center px-6 text-center pt-24 pb-16">

        {/* Pill badge */}
        <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-1.5 mb-8">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-blue-300 text-sm font-medium">Datos en tiempo real · Powered by Binance API</span>
        </div>

        {/* Headline */}
        <h1 className="text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-black leading-[1.05] tracking-tight max-w-5xl mb-6">
          Analiza.{' '}
          <span className="relative">
            <span className="bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
              Opera.
            </span>
          </span>
          <br />
          Domina el{' '}
          <span className="bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
            mercado.
          </span>
        </h1>

        {/* Subtítulo */}
        <p className="text-slate-400 text-lg md:text-xl max-w-2xl mb-10 leading-relaxed">
          Plataforma profesional de análisis técnico, gestión de portfolio y backtesting
          para el mercado de criptomonedas. Todo en un solo lugar, gratis.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-4 items-center mb-14">
          <Link
            to="/register"
            className="group flex items-center gap-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white font-bold px-9 py-4 rounded-2xl text-lg transition-all duration-300 hover:scale-105 hover:shadow-2xl hover:shadow-blue-500/30"
          >
            Empezar gratis
          </Link>
          <Link
            to="/login"
            className="flex items-center gap-2 text-slate-300 hover:text-white font-semibold px-9 py-4 rounded-2xl text-lg border border-slate-700/80 hover:border-slate-500 hover:bg-white/[0.04] transition-all duration-300"
          >
            Ya tengo cuenta
          </Link>
        </div>

        {/* Indicadores de mercado en vivo */}
        {(marketCap || fearGreed != null) && (
          <div className="flex flex-wrap items-center justify-center gap-6 text-sm">
            {marketCap && (
              <div className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2.5">
                <span className="text-slate-400">Market Cap Global</span>
                <span className="font-bold text-white">{marketCap}</span>
              </div>
            )}
            {fearGreed != null && fearLabel && (
              <div className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2.5">
                <span className="text-slate-400">Fear & Greed</span>
                <span className={`font-bold ${fearColor}`}>{fearGreed} · {fearLabel}</span>
              </div>
            )}
          </div>
        )}

        {/* Scroll hint */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1.5 text-slate-600 text-xs animate-bounce">
          <span>Descubre más</span>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </section>

      {/* ════════════════════════════════════════
          TICKER DE PRECIOS
      ════════════════════════════════════════ */}
      <div className="relative z-10 border-y border-white/[0.06] bg-white/[0.015] py-3.5 overflow-hidden">
        <div className="cw-ticker-track flex gap-10 w-max">
          {[...tickers, ...tickers, ...tickers].map((t, i) => (
              <div key={`${t.symbol}-${i}`} className="flex items-center gap-2.5 text-sm shrink-0">
              <span className="font-bold text-white/90">{t.symbol}</span>
              <span className="text-slate-300 tabular-nums">
                ${t.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: t.price < 1 ? 4 : 2 })}
              </span>
              <span className={`text-xs font-semibold tabular-nums ${t.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {t.change >= 0 ? '▲' : '▼'} {Math.abs(t.change).toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ════════════════════════════════════════
          STATS ANIMADAS
      ════════════════════════════════════════ */}
      <section className="relative z-10 py-24 px-6">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 divide-x divide-white/[0.06]">
          <AnimatedStat end={12} suffix="+" label="Indicadores técnicos" />
          <AnimatedStat end={50} suffix="+" label="Criptomonedas disponibles" />
          <AnimatedStat end={1000} suffix="" label="Velas de historial máximo" />
          <AnimatedStat end={24} suffix="/7" label="Datos en tiempo real" />
        </div>
      </section>

      {/* ════════════════════════════════════════
          FEATURES GRID
      ════════════════════════════════════════ */}
      <section className="relative z-10 py-20 px-6">
        <div className="max-w-6xl mx-auto">
          {/* Encabezado */}
          <div className="text-center mb-16">
            <p className="text-blue-400 text-sm font-semibold uppercase tracking-widest mb-3">Funcionalidades</p>
            <h2 className="text-4xl md:text-5xl font-black mb-5 leading-tight">
              Todo lo que necesitas para
              <br />
              <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                operar con ventaja
              </span>
            </h2>
            <p className="text-slate-400 text-lg max-w-xl mx-auto">
              Herramientas de análisis de grado institucional, ahora disponibles para cualquier trader.
            </p>
          </div>

          {/* Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className={`group relative rounded-2xl border ${f.border} bg-gradient-to-br ${f.colorFrom} ${f.colorTo} p-6 backdrop-blur-sm transition-all duration-300 hover:scale-[1.02] hover:shadow-xl ${f.glow} cursor-default`}
              >
                <div className={`w-12 h-12 rounded-xl ${f.iconBg} flex items-center justify-center mb-5`}>
                  {f.icon}
                </div>
                <h3 className="text-white font-bold text-lg mb-2">{f.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════
          TECH STACK
      ════════════════════════════════════════ */}
      <section className="relative z-10 py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-slate-500 text-xs uppercase tracking-[0.2em] mb-8">
            Construido con tecnología de grado profesional
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {TECH_STACK.map((t) => (
              <span
                key={t}
                className="px-4 py-2 text-sm font-medium text-slate-400 border border-slate-800 rounded-xl hover:border-slate-600 hover:text-slate-300 transition-all cursor-default"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════
          CTA FINAL
      ════════════════════════════════════════ */}
      <section className="relative z-10 py-28 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="relative rounded-3xl overflow-hidden border border-blue-500/20 p-12 text-center">
            {/* Fondo degradado del card */}
            <div className="absolute inset-0 bg-gradient-to-br from-blue-600/10 via-purple-600/5 to-transparent" />
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-blue-600/10 rounded-full blur-3xl" />

            <div className="relative">
              <h2 className="text-4xl md:text-5xl font-black mb-4 leading-tight">
                Únete a{' '}
                <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  CryptoWorld
                </span>{' '}
                hoy
              </h2>
              <p className="text-slate-400 text-lg mb-10 max-w-md mx-auto">
                Crea tu cuenta gratuita y empieza a analizar el mercado con herramientas profesionales.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link
                  to="/register"
                  className="group flex items-center justify-center gap-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white font-bold px-10 py-4 rounded-2xl text-lg transition-all hover:scale-105 hover:shadow-2xl hover:shadow-blue-500/30"
                >
                  Crear cuenta gratis
                </Link>
                <Link
                  to="/login"
                  className="flex items-center justify-center text-slate-300 hover:text-white font-semibold px-10 py-4 rounded-2xl text-lg border border-slate-700 hover:border-slate-500 hover:bg-white/[0.04] transition-all"
                >
                  Iniciar sesión
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════
          FOOTER
      ════════════════════════════════════════ */}
      <footer className="relative z-10 border-t border-white/[0.05] py-10 px-6 text-center">
        <div className="flex items-center justify-center gap-2 mb-3">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white">
            <LogoIcon size={12} />
          </div>
          <span className="font-bold text-slate-300">CryptoWorld</span>
        </div>
        <p className="text-slate-600 text-sm">
          TFG · Análisis de Criptomonedas · Universidad de Castilla-La Mancha · 2026
        </p>
        <div className="flex items-center justify-center gap-6 mt-4 text-slate-600 text-sm">
          <Link to="/login" className="hover:text-slate-400 transition-colors">Iniciar sesión</Link>
          <Link to="/register" className="hover:text-slate-400 transition-colors">Registrarse</Link>
        </div>
      </footer>

    </div>
  )
}
