const CACHE = 'muscle-atlas-v135';
// The page asks whether the offline bundle is complete before it tells the user so. Only a list
// written after addAll() resolved counts as complete, so a failed or interrupted precache cannot be
// reported as ready.
const PRECACHE_MANIFEST = '/__precache-manifest.json';
const STATIC_PRECACHE = ['/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png',
  '/models/unified_opensim_skeleton.glb', '/models/unified_muscle_surfaces.glb',
  '/data/unified_opensim_reference.json', '/data/unified_muscle_skin.json',
  '/data/unified_muscle_weights.bin', '/models/NOTICE-unified-opensim.txt',
  '/models/NOTICE-z-anatomy.txt'];
const BEST_EFFORT_PRECACHE = [];
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const response = await fetch('/');
    const html = await response.clone().text();
    const assets = Array.from(html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g), match => match[1]);
    await cache.put('/', response);
    // One URL at a time: a single asset the browser will not store must not take the offline bundle with
    // it. Whatever could not be cached is recorded in the manifest and reported to the page.
    const outcomes = await Promise.all([...STATIC_PRECACHE, ...BEST_EFFORT_PRECACHE, ...assets].map(async url => {
      try {
        await cache.add(url);
        return { url, cached: true };
      } catch (error) {
        return { url, cached: false, reason: String((error && error.message) || error) };
      }
    }));
    const failed = outcomes.filter(outcome => !outcome.cached);
    await cache.put(PRECACHE_MANIFEST, new Response(JSON.stringify({
      cache: CACHE,
      urls: ['/', ...outcomes.filter(outcome => outcome.cached).map(outcome => outcome.url)],
      failed,
    }), { headers: { 'content-type': 'application/json' } }));
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
  if (event.data?.type !== 'cache-status') return;
  event.waitUntil((async () => {
    const port = event.ports[0];
    const cache = await caches.open(CACHE);
    const entries = (await cache.keys()).length;
    const manifest = await cache.match(PRECACHE_MANIFEST);
    if (!manifest) {
      port?.postMessage({ cache: CACHE, complete: false, entries, missing: [PRECACHE_MANIFEST] });
      return;
    }
    const { urls } = await manifest.json();
    const missing = [];
    for (const url of urls) if (!(await cache.match(url))) missing.push(url);
    port?.postMessage({ cache: CACHE, complete: missing.length === 0, entries,
      expected: urls.length, missing });
  })());
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
