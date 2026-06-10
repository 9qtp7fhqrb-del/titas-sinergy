const CACHE_NAME = 'titas-sinergy-v55';

// Install: skip waiting to activate immediately
self.addEventListener('install', event => {
    self.skipWaiting();
});

// Activate: claim all clients so the new SW controls them right away
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

// Fetch: network-first for HTML navigation, cache-first for assets
self.addEventListener('fetch', event => {
    const req = event.request;

    // Only handle GET requests
    if (req.method !== 'GET') return;

    const url = new URL(req.url);

    // For navigation requests (HTML pages), always go network first
    if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
        event.respondWith(
            fetch(req).then(resp => {
                // Cache a fresh copy
                const clone = resp.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
                return resp;
            }).catch(() => caches.match(req))
        );
        return;
    }

    // For everything else: network first, fall back to cache
    event.respondWith(
        fetch(req).then(resp => {
            if (resp && resp.status === 200) {
                const clone = resp.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
            }
            return resp;
        }).catch(() => caches.match(req))
    );
});

// Message handler: force update on demand
self.addEventListener('message', event => {
    if (event.data === 'skipWaiting') self.skipWaiting();
});
