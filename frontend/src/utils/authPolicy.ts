/**
 * utils/authPolicy.ts — Política de credenciales compartida por la interfaz.
 *
 * Los mismos umbrales que aplica el backend (`AUTH_PASSWORD_VALIDATORS`
 * y `PASSWORD_MIN_LENGTH` en settings.py). Estaban repetidos como `8`
 * literal en tres pantallas mientras el servidor exigía otra cosa, así
 * que el formulario dejaba enviar contraseñas que la API rechazaba.
 *
 * La validación real es siempre la del servidor; esto solo evita el
 * viaje de ida y vuelta y da un mensaje inmediato al usuario.
 */

/** Longitud mínima de contraseña (NIST SP 800-63B). */
export const PASSWORD_MIN_LENGTH = 12

/** Texto de ayuda mostrado bajo los campos de contraseña. */
export const PASSWORD_HINT =
  `Elige una contraseña de al menos ${PASSWORD_MIN_LENGTH} caracteres. ` +
  'No puede ser una contraseña común, solo números, ni parecerse a tu email.'

/**
 * Comprueba la longitud mínima antes de enviar el formulario.
 *
 * @returns el mensaje de error, o `null` si la contraseña es aceptable.
 */
export function checkPasswordLength(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres.`
  }
  return null
}
