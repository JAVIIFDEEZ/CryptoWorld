/**
 * pages/Security2FAPage.tsx — Gestión de la autenticación de dos factores.
 *
 * Flujo de activación: generar QR → escanear con la app → confirmar con
 * el primer código TOTP. Al activarse se muestran los códigos de
 * recuperación de un solo uso (única vez que existen en claro): el
 * usuario puede copiarlos o descargarlos como .txt.
 *
 * Con 2FA activo se puede regenerar el juego de códigos (invalida los
 * anteriores) o desactivar 2FA, ambos confirmando con un TOTP vigente.
 */

import { useEffect, useState } from 'react'
import { authService } from '@/services/authService'
import { useToast } from '@/components/ui/Toast'

function RecoveryCodesPanel({ codes }: { codes: string[] }) {
  const { showToast } = useToast()

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(codes.join('\n'))
      showToast('Códigos copiados al portapapeles.', 'success')
    } catch {
      showToast('No se pudieron copiar los códigos.', 'error')
    }
  }

  function handleDownload() {
    const content = [
      'CryptoWorld — Códigos de recuperación 2FA',
      'Cada código solo puede usarse una vez. Guárdalos en un lugar seguro.',
      '',
      ...codes,
    ].join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'cryptoworld-recovery-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-5 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-amber-300">
          Guarda tus códigos de recuperación
        </h3>
        <p className="text-xs text-amber-200/70 mt-1">
          Si pierdes el acceso a tu app autenticadora, estos códigos son la única forma de
          entrar en tu cuenta. Cada uno funciona una sola vez y <strong>no volverán a mostrarse</strong>.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {codes.map((code) => (
          <code
            key={code}
            className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-center text-xs font-mono text-slate-200 tabular-nums"
          >
            {code}
          </code>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleCopy}
          className="text-xs bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded-lg transition-colors"
        >
          Copiar todos
        </button>
        <button
          onClick={handleDownload}
          className="text-xs bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded-lg transition-colors"
        >
          Descargar .txt
        </button>
      </div>
    </div>
  )
}

function Security2FAPage() {
  const { showToast } = useToast()

  const [is2FAEnabled, setIs2FAEnabled] = useState<boolean>(false)
  const [remainingCodes, setRemainingCodes] = useState<number>(0)
  const [qrCodeBase64, setQrCodeBase64] = useState<string | null>(null)
  const [totpEnableCode, setTotpEnableCode] = useState('')
  const [totpDisableCode, setTotpDisableCode] = useState('')
  const [totpRegenerateCode, setTotpRegenerateCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    async function loadMe() {
      try {
        const me = await authService.me()
        setIs2FAEnabled(me.is_2fa_enabled)
        setRemainingCodes(me.recovery_codes_remaining)
      } catch {
        setError('No se pudo cargar el estado de seguridad de la cuenta.')
      }
    }

    loadMe()
  }, [])

  async function handleSetup() {
    setMessage(null)
    setError(null)
    setIsLoading(true)
    try {
      const data = await authService.setup2FA()
      setQrCodeBase64(data.qr_code_base64)
      setMessage('QR generado. Escanéalo en tu app y confirma con un código de 6 dígitos.')
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo iniciar la configuración 2FA.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleEnable() {
    setMessage(null)
    setError(null)
    setIsLoading(true)
    try {
      const response = await authService.enable2FA(totpEnableCode)
      setIs2FAEnabled(true)
      setQrCodeBase64(null)
      setTotpEnableCode('')
      setRecoveryCodes(response.recovery_codes)
      setRemainingCodes(response.recovery_codes.length)
      showToast('2FA activado correctamente.', 'success')
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo activar 2FA.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRegenerateCodes() {
    setMessage(null)
    setError(null)
    setIsLoading(true)
    try {
      const response = await authService.regenerateRecoveryCodes(totpRegenerateCode)
      setTotpRegenerateCode('')
      setRecoveryCodes(response.recovery_codes)
      setRemainingCodes(response.recovery_codes.length)
      showToast('Códigos regenerados. Los anteriores ya no son válidos.', 'success')
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudieron regenerar los códigos.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleDisable() {
    setMessage(null)
    setError(null)
    setIsLoading(true)
    try {
      const response = await authService.disable2FA(totpDisableCode)
      setIs2FAEnabled(false)
      setTotpDisableCode('')
      setRecoveryCodes(null)
      setRemainingCodes(0)
      setMessage(response.message)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo desactivar 2FA.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="space-y-6 max-w-2xl">
      <header>
        <h1 className="text-2xl font-bold text-white">Seguridad 2FA</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configura Google Authenticator/Authy para proteger tu cuenta.
        </p>
      </header>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <p className="text-sm text-slate-300">
            Estado actual:{' '}
            <span className={is2FAEnabled ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold'}>
              {is2FAEnabled ? 'Activado' : 'No activado'}
            </span>
          </p>
          {is2FAEnabled && (
            <p className="text-xs text-slate-500">
              Códigos de recuperación disponibles:{' '}
              <span className={remainingCodes <= 2 ? 'text-amber-400 font-semibold' : 'text-slate-300 font-semibold'}>
                {remainingCodes}
              </span>
            </p>
          )}
        </div>

        {message && <p className="text-sm text-emerald-400">{message}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}

        {!is2FAEnabled && (
          <div className="space-y-4">
            <button
              onClick={handleSetup}
              disabled={isLoading}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm font-semibold px-4 py-2 rounded-lg"
            >
              Generar QR de configuración
            </button>

            {qrCodeBase64 && (
              <div className="space-y-3">
                <img
                  src={qrCodeBase64}
                  alt="QR 2FA"
                  className="w-52 h-52 bg-white p-2 rounded-lg"
                />
                <div>
                  <label className="block text-sm text-slate-300 mb-1">Código de 6 dígitos</label>
                  <input
                    type="text"
                    value={totpEnableCode}
                    onChange={(e) => setTotpEnableCode(e.target.value)}
                    minLength={6}
                    maxLength={6}
                    placeholder="123456"
                    className="w-40 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>
                <button
                  onClick={handleEnable}
                  disabled={isLoading || totpEnableCode.length !== 6}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-800 text-white text-sm font-semibold px-4 py-2 rounded-lg"
                >
                  Activar 2FA
                </button>
              </div>
            )}
          </div>
        )}

        {is2FAEnabled && (
          <div className="space-y-3">
            <label className="block text-sm text-slate-300 mb-1">Código 2FA para desactivar</label>
            <input
              type="text"
              value={totpDisableCode}
              onChange={(e) => setTotpDisableCode(e.target.value)}
              minLength={6}
              maxLength={6}
              placeholder="123456"
              className="w-40 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white"
            />
            <button
              onClick={handleDisable}
              disabled={isLoading || totpDisableCode.length !== 6}
              className="bg-red-600 hover:bg-red-500 disabled:bg-red-800 text-white text-sm font-semibold px-4 py-2 rounded-lg"
            >
              Desactivar 2FA
            </button>
          </div>
        )}
      </div>

      {/* Códigos de recuperación recién generados (única vez visibles) */}
      {recoveryCodes && <RecoveryCodesPanel codes={recoveryCodes} />}

      {/* Regenerar códigos (solo con 2FA activo) */}
      {is2FAEnabled && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-white">Regenerar códigos de recuperación</h2>
            <p className="text-xs text-slate-400 mt-1">
              Genera un juego nuevo de 10 códigos. Los anteriores quedarán invalidados
              inmediatamente. Confirma con un código de tu app autenticadora.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={totpRegenerateCode}
              onChange={(e) => setTotpRegenerateCode(e.target.value)}
              minLength={6}
              maxLength={6}
              placeholder="123456"
              aria-label="Código TOTP para regenerar códigos"
              className="w-40 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white"
            />
            <button
              onClick={handleRegenerateCodes}
              disabled={isLoading || totpRegenerateCode.length !== 6}
              className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg border border-slate-600"
            >
              Regenerar códigos
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

export default Security2FAPage
