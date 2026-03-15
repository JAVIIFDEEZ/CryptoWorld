import { useEffect, useState } from 'react'
import { authService } from '@/services/authService'

function Security2FAPage() {
  const [is2FAEnabled, setIs2FAEnabled] = useState<boolean>(false)
  const [qrCodeBase64, setQrCodeBase64] = useState<string | null>(null)
  const [totpEnableCode, setTotpEnableCode] = useState('')
  const [totpDisableCode, setTotpDisableCode] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    async function loadMe() {
      try {
        const me = await authService.me()
        setIs2FAEnabled(me.is_2fa_enabled)
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
      setMessage('QR generado. Escanealo en tu app y confirma con un codigo de 6 digitos.')
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo iniciar la configuracion 2FA.')
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
      setMessage(response.message)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo activar 2FA.')
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
      setMessage(response.message)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { error?: string } } }
      setError(axiosError?.response?.data?.error ?? 'No se pudo desactivar 2FA.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Seguridad 2FA</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configura Google Authenticator/Authy para proteger tu cuenta.
        </p>
      </header>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4">
        <p className="text-sm text-slate-300">
          Estado actual:{' '}
          <span className={is2FAEnabled ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold'}>
            {is2FAEnabled ? 'Activado' : 'No activado'}
          </span>
        </p>

        {message && <p className="text-sm text-emerald-400">{message}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}

        {!is2FAEnabled && (
          <div className="space-y-4">
            <button
              onClick={handleSetup}
              disabled={isLoading}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm font-semibold px-4 py-2 rounded-lg"
            >
              Generar QR de configuracion
            </button>

            {qrCodeBase64 && (
              <div className="space-y-3">
                <img
                  src={`data:image/png;base64,${qrCodeBase64}`}
                  alt="QR 2FA"
                  className="w-52 h-52 bg-white p-2 rounded-lg"
                />
                <div>
                  <label className="block text-sm text-slate-300 mb-1">Codigo de 6 digitos</label>
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
            <label className="block text-sm text-slate-300 mb-1">Codigo 2FA para desactivar</label>
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
    </section>
  )
}

export default Security2FAPage
