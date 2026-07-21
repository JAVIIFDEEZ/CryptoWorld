/**
 * services/pushService.ts — Suscripción a Web Push (PWA).
 *
 * Registra el navegador para recibir notificaciones push (kill-switch de
 * ejecución real, alertas de precio, confluencia) aunque la app esté cerrada.
 * Degrada con elegancia: si el navegador no soporta push, o el backend no tiene
 * claves VAPID, no hace nada (el WebSocket y el centro in-app siguen).
 */

import apiClient from './api'

function urlBase64ToUint8Array(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64)
  const buf = new ArrayBuffer(raw.length)
  const view = new Uint8Array(buf)
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i)
  return buf
}

export const pushService = {
  /** ¿El navegador soporta Web Push? */
  supported(): boolean {
    return typeof window !== 'undefined'
      && 'serviceWorker' in navigator
      && 'PushManager' in window
      && 'Notification' in window
  },

  /** Estado actual del permiso ('default' | 'granted' | 'denied'). */
  permission(): NotificationPermission {
    return this.supported() ? Notification.permission : 'denied'
  },

  /**
   * Pide permiso, se suscribe con la clave VAPID del backend y registra la
   * suscripción. Devuelve true si quedó suscrito. Idempotente.
   */
  async subscribe(): Promise<boolean> {
    if (!this.supported()) return false
    const { data: cfg } = await apiClient.get<{ public_key: string | null; enabled: boolean }>('/push/public-key/')
    if (!cfg.enabled || !cfg.public_key) return false   // backend sin claves VAPID

    const perm = await Notification.requestPermission()
    if (perm !== 'granted') return false

    const reg = await navigator.serviceWorker.ready
    const existing = await reg.pushManager.getSubscription()
    const sub = existing ?? await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
    })
    const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } }
    await apiClient.post('/push/subscribe/', {
      endpoint: json.endpoint,
      keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
    })
    return true
  },

  /** Cancela la suscripción del navegador y la borra en el backend. */
  async unsubscribe(): Promise<void> {
    if (!this.supported()) return
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    if (!sub) return
    const endpoint = sub.endpoint
    await sub.unsubscribe().catch(() => { /* ignore */ })
    await apiClient.delete('/push/subscribe/', { data: { endpoint } }).catch(() => { /* ignore */ })
  },
}
