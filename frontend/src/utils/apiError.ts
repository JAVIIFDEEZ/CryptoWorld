/**
 * utils/apiError.ts — Lectura del contrato de error de la API.
 *
 * El backend responde a cualquier error con una envolvente única:
 *
 *   {
 *     "error": { "code": "...", "message": "...", "details": { ... } },
 *     "request_id": "3f2a…"
 *   }
 *
 * Antes cada pantalla leía `response.data.error` esperando una cadena, y
 * el backend devolvía a veces una cadena, a veces `detail`, a veces el
 * diccionario crudo del serializer. Este módulo es el único sitio que
 * conoce la forma de la respuesta: el resto de la aplicación pide el
 * mensaje y recibe siempre un string listo para pintar.
 */

/** Códigos de error estables que la interfaz trata de forma específica. */
export type ApiErrorCode =
  | 'validation_error'
  | 'invalid_credentials'
  | 'email_not_verified'
  | 'account_disabled'
  | 'account_locked'
  | 'session_revoked'
  | 'rate_limit_exceeded'
  | 'not_found'
  | 'permission_denied'
  | 'superuser_required'
  | 'internal_error'
  | (string & {})

export interface ApiError {
  code: ApiErrorCode
  message: string
  /** Errores campo a campo de un fallo de validación. */
  details?: Record<string, string[] | string>
  /** Identificador de correlación, útil al reportar una incidencia. */
  requestId?: string
  status?: number
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: Record<string, unknown> }
  request_id?: string
  /** Formas heredadas, por si algún endpoint no pasa por el manejador. */
  detail?: string
}

/**
 * Normaliza cualquier error de Axios al tipo `ApiError`.
 *
 * @param err       error capturado (normalmente de Axios).
 * @param fallback  mensaje a mostrar si la respuesta no trae uno.
 */
export function parseApiError(err: unknown, fallback = 'Se ha producido un error.'): ApiError {
  const response = (err as { response?: { status?: number; data?: ErrorEnvelope } })?.response
  const data = response?.data

  if (data?.error) {
    return {
      code: data.error.code ?? 'error',
      message: data.error.message || fallback,
      details: normalizeDetails(data.error.details),
      requestId: data.request_id,
      status: response?.status,
    }
  }

  if (typeof data?.detail === 'string') {
    return { code: 'error', message: data.detail, status: response?.status }
  }

  // Sin respuesta del servidor: el fallo es de red o de tiempo de espera.
  if (!response) {
    return {
      code: 'network_error',
      message: 'No se ha podido contactar con el servidor. Revisa tu conexión.',
    }
  }

  return { code: 'error', message: fallback, status: response.status }
}

/** Atajo para el caso más común: solo se necesita el texto a mostrar. */
export function apiErrorMessage(err: unknown, fallback = 'Se ha producido un error.'): string {
  return parseApiError(err, fallback).message
}

/**
 * Mensaje del primer error de un campo concreto.
 *
 * Útil en formularios donde interesa colocar el aviso junto al input
 * (por ejemplo `new_password` en el restablecimiento de contraseña).
 */
export function fieldError(err: unknown, field: string): string | undefined {
  const details = parseApiError(err).details
  const value = details?.[field]
  if (!value) return undefined
  return Array.isArray(value) ? value[0] : value
}

/**
 * Mensaje combinado: el del campo indicado si existe, si no el general.
 */
export function apiErrorFor(err: unknown, field: string, fallback: string): string {
  return fieldError(err, field) ?? apiErrorMessage(err, fallback)
}

function normalizeDetails(
  raw: Record<string, unknown> | undefined,
): Record<string, string[] | string> | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const out: Record<string, string[] | string> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (Array.isArray(value)) {
      out[key] = value.map(String)
    } else if (value != null) {
      out[key] = String(value)
    }
  }
  return Object.keys(out).length ? out : undefined
}
