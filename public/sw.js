const CACHE = 'muscle-atlas-v109';
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const response = await fetch('/');
    const html = await response.clone().text();
    const assets = Array.from(html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g), match => match[1]);
    await cache.put('/', response);
    await cache.addAll(['/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png',
      '/models/prototype_parts.glb', '/models/z_anatomy_reference.glb', '/models/NOTICE-z-anatomy.txt',
      '/data/squat_opensim_reference.json', '/data/press_tsm_reference.json',
      '/data/bench_tsm_reference.json', ...assets]);
  })());
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('muscle-atlas-') && key !== CACHE).map(key => caches.delete(key)))),
    self.clients.claim(),
  ]));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'cache-status') event.ports[0]?.postMessage({ cache: CACHE });
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(async response => {
      if (response.ok) return response;
      return await caches.match('/') ?? response;
    }).catch(() => caches.match('/')));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached => cached ?? fetch(event.request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      void caches.open(CACHE).then(cache => cache.put(event.request, copy));
    }
    return response;
  })));
});
