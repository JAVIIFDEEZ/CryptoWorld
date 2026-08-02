/**
 * pages/TradingPage.tsx — Trading real multi-exchange (ejecución manual).
 *
 * Conecta exchanges vía claves API (cifradas en el backend, verificadas antes de
 * guardar, TESTNET por defecto), consulta saldos y lanza órdenes market/limit
 * con confirmación. Cada orden es una decisión explícita del usuario: aquí no
 * hay automatismos. El modo real se señala de forma inequívoca.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  EXCHANGES,
  tradingService,
  type BrokerBalance,
  type BrokerOrder,
  type ExchangeConnection,
  type ExchangeId,
} from '@/services/tradingService'
import { useToast } from '@/components/ui/Toast'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import ExecutionAuditPanel from '@/components/trading/ExecutionAuditPanel'
import { useTranslation } from 'react-i18next'

function ModeBadge({ testnet }: Readonly<{ testnet: boolean }>) {
  const { t } = useTranslation()
  return testnet ? (
    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/30">{t('trading.testnetBadge')}</span>
  ) : (
    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse">{t('trading.realBadge')}</span>
  )
}

export default function TradingPage() {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const [connections, setConnections] = useState<ExchangeConnection[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [balance, setBalance] = useState<BrokerBalance | null>(null)
  const [orders, setOrders] = useState<BrokerOrder[]>([])
  const [loadingConn, setLoadingConn] = useState(true)
  const [busy, setBusy] = useState(false)

  // Alta de conexión
  const [showAdd, setShowAdd] = useState(false)
  const [exchange, setExchange] = useState<ExchangeId>('binance')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [apiPassword, setApiPassword] = useState('')
  const [testnet, setTestnet] = useState(true)
  const [label, setLabel] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  // Formulario de orden
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [amount, setAmount] = useState('')
  const [price, setPrice] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const selected = connections.find((c) => c.id === selectedId) ?? null
  const sandboxCapable = EXCHANGES.find((e) => e.id === exchange)?.sandbox ?? false

  const reloadConnections = useCallback(() => {
    tradingService.listConnections()
      .then((list) => {
        setConnections(list)
        setSelectedId((cur) => cur ?? list[0]?.id ?? null)
      })
      .catch(() => { /* sin conexiones */ })
      .finally(() => setLoadingConn(false))
  }, [])

  useEffect(() => { reloadConnections() }, [reloadConnections])

  const reloadBroker = useCallback(() => {
    if (!selectedId) { setBalance(null); setOrders([]); return }
    tradingService.getBalance(selectedId).then(setBalance).catch(() => setBalance(null))
    tradingService.openOrders(selectedId).then(setOrders).catch(() => setOrders([]))
  }, [selectedId])

  useEffect(() => { reloadBroker() }, [reloadBroker])

  async function handleConnect() {
    setBusy(true); setAddError(null)
    try {
      await tradingService.connect({
        exchange,
        api_key: apiKey,
        api_secret: apiSecret,
        api_password: apiPassword || undefined,
        is_testnet: testnet,
        label: label || undefined,
      })
      setShowAdd(false)
      setApiKey(''); setApiSecret(''); setApiPassword(''); setLabel('')
      showToast('Exchange conectado y verificado.', 'success')
      reloadConnections()
    } catch (e: unknown) {
      const resp = (e as { response?: { data?: { error?: string } } })?.response
      setAddError(resp?.data?.error ?? 'No se pudo conectar el exchange.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDisconnect(id: number) {
    try {
      await tradingService.disconnect(id)
      setSelectedId(null)
      showToast('Exchange desconectado.', 'success')
      reloadConnections()
    } catch { showToast('No se pudo desconectar.', 'error') }
  }

  function requestOrder() {
    if (!selected) return
    setConfirmOpen(true)
  }

  async function handlePlaceOrder() {
    if (!selected) return
    setConfirmOpen(false)
    setBusy(true)
    try {
      const r = await tradingService.placeOrder(selected.id, {
        symbol: symbol.trim().toUpperCase(),
        side,
        type: orderType,
        amount: Number.parseFloat(amount),
        ...(orderType === 'limit' ? { price: Number.parseFloat(price) } : {}),
      })
      const replayed = r.idempotent_replay ? ' (reintento: no se duplicó)' : ''
      showToast(
        `Orden ${r.order.side} ${r.order.symbol} enviada (${r.is_testnet ? 'testnet' : 'REAL'})${replayed}.`,
        'success',
      )
      setAmount(''); setPrice('')
      reloadBroker()
    } catch (e: unknown) {
      const resp = (e as { response?: { status?: number; data?: { error?: string; blocked_by?: string } } })?.response
      // 409 = la orden es válida pero la frena la política de riesgo del propio
      // usuario. Merece un mensaje distinto de un error de formato o de red.
      if (resp?.status === 409 && resp.data?.blocked_by === 'oms') {
        showToast(`Bloqueada por tu límite de riesgo: ${resp.data.error}`, 'error')
      } else {
        showToast(resp?.data?.error ?? 'No se pudo enviar la orden.', 'error')
      }
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel(o: BrokerOrder) {
    if (!selected || !o.symbol) return
    try {
      await tradingService.cancelOrder(selected.id, o.id, o.symbol)
      showToast('Orden cancelada.', 'success')
      reloadBroker()
    } catch { showToast('No se pudo cancelar la orden.', 'error') }
  }

  return (
    <section className="space-y-6">
      {/* Cabecera */}
      <header>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-white">{t('trading.title')}</h1>
          <span className="text-[10px] font-semibold uppercase tracking-wider bg-gradient-to-r from-emerald-500/20 to-sky-500/20 text-emerald-300 border border-emerald-500/30 rounded-full px-2 py-0.5">
            {t('trading.badge')}
          </span>
        </div>
        <p className="text-slate-400 text-sm mt-1 max-w-2xl">
          {t('trading.subtitle1')}
          <span className="text-sky-300 font-medium"> {t('trading.subtitleTestnet')}</span>{t('trading.subtitle2')}
        </p>
      </header>

      {/* OMS: límite de pérdida diaria de la ejecución real */}
      <RiskPolicyCard />

      {/* Auditoría de cumplimiento de la ejecución real */}
      <ExecutionAuditPanel />

      {/* Conexiones */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <h2 className="text-sm font-semibold text-white">{t('trading.connections')}</h2>
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors"
          >
            {showAdd ? t('trading.close') : t('trading.connect')}
          </button>
        </div>

        {showAdd && (
          <div className="bg-slate-900/50 rounded-lg border border-slate-700/60 p-4 mb-3 space-y-3">
            <div className="flex flex-wrap gap-3">
              <label className="text-[11px] text-slate-400">
                <span className="block mb-1 uppercase">Exchange</span>
                <select value={exchange} onChange={(e) => { const ex = e.target.value as ExchangeId; setExchange(ex); if (!(EXCHANGES.find(x => x.id === ex)?.sandbox)) setTestnet(false) }}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
                  {EXCHANGES.map((e) => <option key={e.id} value={e.id}>{e.label}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-slate-400 flex-1 min-w-[200px]">
                <span className="block mb-1 uppercase">API key</span>
                <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} spellCheck={false}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
              </label>
              <label className="text-[11px] text-slate-400 flex-1 min-w-[200px]">
                <span className="block mb-1 uppercase">API secret</span>
                <input value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} type="password" spellCheck={false}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
              </label>
              {exchange === 'okx' && (
                <label className="text-[11px] text-slate-400">
                  <span className="block mb-1 uppercase">Passphrase</span>
                  <input value={apiPassword} onChange={(e) => setApiPassword(e.target.value)} type="password"
                    className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
                </label>
              )}
              <label className="text-[11px] text-slate-400">
                <span className="block mb-1 uppercase">Alias</span>
                <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="opcional"
                  className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" />
              </label>
            </div>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <label className={`flex items-center gap-2 text-xs ${sandboxCapable ? 'text-slate-300' : 'text-slate-600'}`}>
                <input type="checkbox" checked={testnet} disabled={!sandboxCapable}
                  onChange={(e) => setTestnet(e.target.checked)} className="accent-sky-500" />
                Modo testnet (dinero ficticio{sandboxCapable ? ', recomendado' : ' — no disponible en este exchange'})
              </label>
              <button onClick={handleConnect} disabled={busy || !apiKey.trim() || !apiSecret.trim()}
                className="text-xs px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-50">
                {busy ? t('trading.verifying') : t('trading.verifyConnect')}
              </button>
            </div>
            {!testnet && (
              <p className="text-[11px] text-red-300 bg-red-900/20 border border-red-700/40 rounded-lg px-3 py-2">
                ⚠ Esta conexión operará con DINERO REAL. Usa una API key con permisos solo de lectura+trading
                (nunca retiradas) y limita su IP en el exchange.
              </p>
            )}
            {addError && <p className="text-xs text-red-400">{addError}</p>}
          </div>
        )}

        {loadingConn && <p className="text-sm text-slate-500">Cargando…</p>}
        {!loadingConn && connections.length === 0 && !showAdd && (
          <p className="text-sm text-slate-500">
            {t('trading.noConnections')}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {connections.map((c) => (
            <button key={c.id} onClick={() => setSelectedId(c.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
                selectedId === c.id ? 'border-blue-500 bg-blue-600/10 text-white' : 'border-slate-700 bg-slate-900/40 text-slate-300 hover:border-slate-500'
              }`}>
              <span className="font-medium capitalize">{c.exchange}</span>
              {c.label && <span className="text-slate-500 text-xs">{c.label}</span>}
              <ModeBadge testnet={c.is_testnet} />
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => { e.stopPropagation(); handleDisconnect(c.id) }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); handleDisconnect(c.id) } }}
                className="text-slate-600 hover:text-red-400" title="Desconectar">✕</span>
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Balance */}
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white">{t('trading.balance')} · <span className="capitalize">{selected.exchange}</span></h2>
              <div className="flex items-center gap-2">
                <ModeBadge testnet={selected.is_testnet} />
                <button onClick={reloadBroker} className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-700">⟳</button>
              </div>
            </div>
            {!balance && <p className="text-sm text-slate-500">No se pudo cargar el balance.</p>}
            {balance && balance.balances.length === 0 && (
              <p className="text-sm text-slate-500">Sin saldos (en testnet, pide fondos de prueba al faucet del exchange).</p>
            )}
            {balance && balance.balances.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-700/60">
                    <th className="text-left py-1.5">{t('trading.asset')}</th>
                    <th className="text-right py-1.5">{t('trading.free')}</th>
                    <th className="text-right py-1.5">{t('trading.inOrders')}</th>
                    <th className="text-right py-1.5">{t('trading.total')}</th>
                  </tr>
                </thead>
                <tbody>
                  {balance.balances.slice(0, 12).map((b) => (
                    <tr key={b.asset} className="border-b border-slate-800 last:border-0">
                      <td className="py-1.5 font-semibold text-slate-200">{b.asset}</td>
                      <td className="py-1.5 text-right font-mono text-slate-300">{b.free.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                      <td className="py-1.5 text-right font-mono text-slate-500">{b.used.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                      <td className="py-1.5 text-right font-mono text-white">{b.total.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Nueva orden */}
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
            <h2 className="text-sm font-semibold text-white mb-3">{t('trading.newOrder')}</h2>
            <div className="space-y-3">
              <div className="flex flex-wrap gap-3">
                <label className="text-[11px] text-slate-400 flex-1 min-w-[140px]">
                  <span className="block mb-1 uppercase">{t('trading.pair')}</span>
                  <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="BTC/USDT" spellCheck={false}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
                </label>
                <label className="text-[11px] text-slate-400">
                  <span className="block mb-1 uppercase">{t('trading.side')}</span>
                  <div className="flex gap-0.5 bg-slate-900 rounded-lg p-0.5">
                    <button onClick={() => setSide('buy')}
                      className={`px-4 py-1.5 rounded-md text-xs font-bold ${side === 'buy' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}>{t('trading.buy')}</button>
                    <button onClick={() => setSide('sell')}
                      className={`px-4 py-1.5 rounded-md text-xs font-bold ${side === 'sell' ? 'bg-red-600 text-white' : 'text-slate-400'}`}>{t('trading.sell')}</button>
                  </div>
                </label>
                <label className="text-[11px] text-slate-400">
                  <span className="block mb-1 uppercase">{t('trading.type')}</span>
                  <div className="flex gap-0.5 bg-slate-900 rounded-lg p-0.5">
                    <button onClick={() => setOrderType('market')}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium ${orderType === 'market' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}>Market</button>
                    <button onClick={() => setOrderType('limit')}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium ${orderType === 'limit' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}>Limit</button>
                  </div>
                </label>
              </div>
              <div className="flex flex-wrap gap-3">
                <label className="text-[11px] text-slate-400">
                  <span className="block mb-1 uppercase">{t('trading.amountBase')}</span>
                  <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" min="0" step="any" placeholder="0.001"
                    className="w-36 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
                </label>
                {orderType === 'limit' && (
                  <label className="text-[11px] text-slate-400">
                    <span className="block mb-1 uppercase">{t('trading.price')}</span>
                    <input value={price} onChange={(e) => setPrice(e.target.value)} type="number" min="0" step="any" placeholder="60000"
                      className="w-36 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono" />
                  </label>
                )}
                <div className="flex-1" />
                <button onClick={requestOrder}
                  disabled={busy || !amount || (orderType === 'limit' && !price)}
                  className={`self-end text-sm font-bold px-5 py-2 rounded-lg text-white transition-colors disabled:opacity-50 ${
                    side === 'buy' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500'
                  }`}>
                  {side === 'buy' ? t('trading.buy') : t('trading.sell')} {symbol.split('/')[0] || ''}
                </button>
              </div>
              {!selected.is_testnet && (
                <p className="text-[11px] text-red-300">⚠ Conexión en modo DINERO REAL: la orden se ejecutará en el mercado.</p>
              )}
            </div>

            {/* Órdenes abiertas */}
            <div className="mt-4 border-t border-slate-700/60 pt-3">
              <p className="text-[10px] text-slate-500 uppercase mb-2">{t('trading.openOrders')}</p>
              {orders.length === 0 && <p className="text-xs text-slate-500">{t('trading.none')}</p>}
              {orders.map((o) => (
                <div key={o.id} className="flex items-center gap-2 text-xs py-1.5 border-b border-slate-800 last:border-0">
                  <span className={`font-bold px-1.5 py-0.5 rounded text-[10px] ${o.side === 'buy' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>
                    {o.side?.toUpperCase()}
                  </span>
                  <span className="text-slate-200 font-mono">{o.symbol}</span>
                  <span className="text-slate-400 font-mono">{o.amount}</span>
                  {o.price != null && <span className="text-slate-500 font-mono">@ {o.price}</span>}
                  <span className="ml-auto text-slate-600">{o.status}</span>
                  <button onClick={() => handleCancel(o)} className="text-slate-500 hover:text-red-400" title="Cancelar">✕</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600">
        Las credenciales se cifran en el servidor y nunca se devuelven. Recomendado: claves con permisos
        solo de lectura+trading (sin retiradas) y restricción de IP. Nada de esto es asesoramiento financiero.
      </p>

      <ConfirmDialog
        open={confirmOpen}
        title={selected?.is_testnet ? 'Confirmar orden (testnet)' : '⚠ Confirmar orden con DINERO REAL'}
        description={`${side === 'buy' ? 'Comprar' : 'Vender'} ${amount} ${symbol.split('/')[0] ?? ''} en ${symbol} (${orderType}${orderType === 'limit' ? ` @ ${price}` : ''}) vía ${selected?.exchange ?? ''}${selected?.is_testnet ? ' · dinero ficticio' : ' · SE EJECUTARÁ EN EL MERCADO REAL'}.`}
        confirmLabel="Enviar orden"
        tone={selected?.is_testnet ? 'primary' : 'danger'}
        onConfirm={handlePlaceOrder}
        onCancel={() => setConfirmOpen(false)}
      />
    </section>
  )
}


function RiskPolicyCard() {
  const [limit, setLimit] = useState<string>('')
  const [conc, setConc] = useState<string>('')
  const [current, setCurrent] = useState<number | null>(null)
  const [today, setToday] = useState<number>(0)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    tradingService.getRiskPolicy()
      .then((p) => {
        setCurrent(p.daily_loss_limit_usd)
        setLimit(p.daily_loss_limit_usd != null ? String(p.daily_loss_limit_usd) : '')
        setConc(p.max_concentration_pct != null ? String(p.max_concentration_pct) : '')
        setToday(p.realized_today_usd ?? 0)
      })
      .catch(() => { /* sin política */ })
  }, [])

  async function save() {
    setSaving(true)
    try {
      const lv = limit.trim() === '' ? null : Number.parseFloat(limit)
      const cv = conc.trim() === '' ? null : Number.parseFloat(conc)
      const p = await tradingService.setRiskPolicy({
        daily_loss_limit_usd: Number.isFinite(lv as number) ? (lv as number) : null,
        max_concentration_pct: Number.isFinite(cv as number) ? (cv as number) : null,
      })
      setCurrent(p.daily_loss_limit_usd)
      setLimit(p.daily_loss_limit_usd != null ? String(p.daily_loss_limit_usd) : '')
      setConc(p.max_concentration_pct != null ? String(p.max_concentration_pct) : '')
    } catch { /* se muestra el estado anterior */ }
    finally { setSaving(false) }
  }

  const breached = current != null && today <= -current
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex-1 min-w-[220px]">
          <h2 className="text-sm font-semibold text-white">🛡 Controles de riesgo (OMS)</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Ambos bloquean nuevas COMPRAS en real; las ventas nunca se bloquean. Vacío = sin límite.
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-500 uppercase">P&L realizado hoy</p>
          <p className={`text-sm font-bold font-mono ${today < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
            {today >= 0 ? '+' : ''}{today.toLocaleString(undefined, { maximumFractionDigits: 2 })} $
          </p>
        </div>
      </div>
      <div className="flex items-end gap-4 flex-wrap mt-3">
        <label className="text-[11px] text-slate-400">
          <span className="block mb-1">Pérdida diaria máx.</span>
          <span className="flex items-center gap-1">
            <input
              type="number" min={10} step={10} value={limit}
              onChange={(e) => setLimit(e.target.value)} placeholder="p. ej. 100"
              className="w-28 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-xs text-slate-500">USD/día</span>
          </span>
        </label>
        <label className="text-[11px] text-slate-400">
          <span className="block mb-1">Concentración máx. por activo</span>
          <span className="flex items-center gap-1">
            <input
              type="number" min={5} max={100} step={5} value={conc}
              onChange={(e) => setConc(e.target.value)} placeholder="p. ej. 30"
              className="w-24 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-xs text-slate-500">% del libro</span>
          </span>
        </label>
        <button
          onClick={save}
          disabled={saving}
          className="text-xs px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
        >
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
      {breached && (
        <p className="text-[11px] text-amber-300 mt-2">
          ⚠ Límite de pérdida alcanzado hoy: las compras en real están bloqueadas hasta mañana.
        </p>
      )}
    </div>
  )
}
