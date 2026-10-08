/* El caché contiene exclusivamente la interfaz pública, nunca respuestas privadas de PMANT. */
const CACHE = "pmant-offline-shell-19.0.2.30.0-1";
const ASSETS = ["/pmant/offline", "/pmant/static/offline/app.js", "/pmant/static/offline/core.js", "/pmant/static/offline/app.css", "/pmant/static/offline/icon.svg", "/pmant/static/src/img/img_empresa.png", "/pmant/static/offline/manifest.webmanifest"];
self.addEventListener("install", event => event.waitUntil((async () => {
    await (await caches.open(CACHE)).addAll(ASSETS.map(path => new Request(path, {cache: "reload"})));
    await self.skipWaiting();
})()));
self.addEventListener("activate", event => event.waitUntil((async () => {
    for (const name of await caches.keys()) if (name.startsWith("pmant-offline-shell-") && name !== CACHE) await caches.delete(name);
    await self.clients.claim();
})()));
self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);
    if (event.request.method !== "GET" || url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
    event.respondWith((async () => {
        const cache = await caches.open(CACHE);
        const cached = await cache.match(url.pathname);
        return cached || fetch(event.request);
    })());
});

