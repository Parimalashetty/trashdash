/* ─── TrashDash Service Worker ───────────────────────────────────
   Provides offline support and asset caching for PWA install.
─────────────────────────────────────────────────────────────────── */
const CACHE_NAME = 'trashdash-cache-v2';
 
// Assets to pre-cache on install
const PRE_CACHE = [
  '/',
  '/manifest.json',
  'https://fonts.googleapis.com/css2?family=Boogaloo&family=Nunito:wght@400;600;700;800;900&display=swap',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
];
 
// ─── Install ──────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRE_CACHE))
      .then(() => self.skipWaiting())
  );
});
 
// ─── Activate: clear old caches ───────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});
 
// ─── Fetch: network-first, cache fallback ─────────────────────────
self.addEventListener('fetch', event => {
  // Skip non-GET and API calls (always need fresh data)
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/'))  return;
 
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
 
// ─── Push notifications (future use) ─────────────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'TrashDash', {
    body:  data.body  || 'Your waste collector is nearby!',
    icon:  data.icon  || '/manifest.json',
    badge: data.badge || '/manifest.json',
    tag:   'trashdash-notification',
    renotify: true,
    data: { url: data.url || '/' }
  });
});
 
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
