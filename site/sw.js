// Service worker: keeps a copy of the whole site so it works offline (and as a
// home-screen app). build_site.py fills in VERSION and the file lists; a new
// deploy changes VERSION, so the browser fetches the new files in the background
// and uses them from the next visit.
const VERSION = "__VERSION__";
const SITE = `site-${VERSION}`;
const SOUNDS = "sounds-__SOUNDS_VERSION__";  // the piano notes (2 MB) change rarely: cached apart
const SITE_FILES = __SITE_FILES__;
const SOUND_FILES = __SOUND_FILES__;

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    // cache: "reload" skips the browser's HTTP cache, which may still hold the old files.
    const fresh = (files) => files.map((f) => new Request(f, { cache: "reload" }));
    await (await caches.open(SITE)).addAll(fresh(SITE_FILES));
    const sounds = await caches.open(SOUNDS);
    const have = new Set((await sounds.keys()).map((r) => r.url));
    await sounds.addAll(fresh(SOUND_FILES.filter((f) => !have.has(new URL(f, location).href))));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name !== SITE && name !== SOUNDS) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || new URL(request.url).origin !== location.origin) return;
  // Every page (?tune=…, ?page=…) is the same index.html.
  const key = request.mode === "navigate" ? "./" : request;
  event.respondWith((async () =>
    (await caches.match(key, { ignoreSearch: request.mode === "navigate" })) ?? fetch(request))());
});
