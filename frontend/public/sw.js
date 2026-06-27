/*
 * sw.js — Service worker de CryptoWorld (PWA, sin dependencias).
 *
 * Estrategia conservadora y segura:
 *   · Solo intercepta GET del mismo origen; NUNCA toca /api (datos siempre frescos).
 *   · Navegaciones: network-first con respaldo al shell cacheado (offline).
 *   · Estáticos (JS/CSS/fuentes/imágenes): stale-while-revalidate.
 */

const CACHE = 'cw-runtime-v1'

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return

  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api')) return

  // Navegaciones de la SPA: red primero, respaldo al shell cacheado sin conexión.
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req)
        const cache = await caches.open(CACHE)
        cache.put('/', fresh.clone())
        return fresh
      } catch {
        return (await caches.match('/')) || Response.error()
      }
    })())
    return
  }

  // Estáticos del mismo origen: responde de caché y revalida en segundo plano.
  event.respondWith((async () => {
    const cache = await caches.open(CACHE)
    const cached = await cache.match(req)
    const network = fetch(req)
      .then((res) => {
        if (res && res.status === 200) cache.put(req, res.clone())
        return res
      })
      .catch(() => cached)
    return cached || network
  })())
})
