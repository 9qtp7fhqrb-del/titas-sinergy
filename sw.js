const CACHE_NAME = 'titas-sinergy-v57';

// Install: ativa imediatamente, sem esperar aba fechar
self.addEventListener('install', event => {
    event.waitUntil(self.skipWaiting());
});

// Activate: apaga TODOS os caches e força reload de todas as abas abertas
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.map(k => caches.delete(k))))
            .then(() => self.clients.claim())
            .then(() => self.clients.matchAll({ type: 'window', includeUncontrolled: true }))
            .then(clients => {
                return Promise.all(clients.map(client => {
                    // Força reload da aba com a URL atual (busca direto do servidor)
                    try { return client.navigate(client.url); } catch(e) { return Promise.resolve(); }
                }));
            })
    );
});

// Fetch: sempre busca do servidor, sem cache
self.addEventListener('fetch', event => {
    const req = event.request;
    if (req.method !== 'GET') return;
    event.respondWith(
        fetch(req, { cache: 'no-store' }).catch(() => caches.match(req))
    );
});

self.addEventListener('message', event => {
    if (event.data === 'skipWaiting') self.skipWaiting();
});
