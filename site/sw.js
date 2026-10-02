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
    await self.skipWaiting();
  })());
});

// The piano notes aren't all fetched at first (2 MB, on a phone's data): each is kept
// the first time it's played (see "fetch"), and the app asks for the rest, "save-sounds",
// where data is cheap or the site is installed, or when the reader asks. "sounds?" asks
// how many are kept; either way the answer is { sounds: { saved, total } }.
async function soundsMissing() {
  const have = new Set((await (await caches.open(SOUNDS)).keys()).map((r) => r.url));
  return SOUND_FILES.filter((f) => !have.has(new URL(f, location).href));
}

self.addEventListener("message", (event) => {
  const answer = async () => {
    const missing = await soundsMissing();
    event.source?.postMessage({ sounds: { saved: SOUND_FILES.length - missing.length, total: SOUND_FILES.length } });
  };
  if (event.data === "sounds?") event.waitUntil(answer());
  if (event.data === "save-sounds") {
    event.waitUntil((async () => {
      const missing = await soundsMissing();
      await (await caches.open(SOUNDS)).addAll(missing.map((f) => new Request(f, { cache: "reload" }))).catch(() => {});
      await answer();
    })());
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name !== SITE && name !== SOUNDS) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

// The app itself (its pages, code, styles and tune list) comes from the network when
// it answers within FRESH_WAIT ms, so a new version is used at once (an older copy
// might not know a newer kind of link: a set's, say). Offline or on a very slow
// connection, it's the saved copy. "no-cache" asks the server whether the file has
// changed, past the browser's own short-term cache (GitHub Pages: 10 minutes).
// Everything else (the piano notes, the map, the libraries) is used from the copy; a
// piano note not kept yet is fetched, and kept.
const FRESH_WAIT = 2000;
const FRESH = new Set(["", "index.html", "app.js", "style.css", "tunes.json"]);

async function freshOrSaved(url, saved) {
  try {
    const answer = await Promise.race([
      fetch(url, { cache: "no-cache" }),
      new Promise((_, reject) => setTimeout(() => reject(new Error("slow")), FRESH_WAIT)),
    ]);
    if (answer.ok) return answer;
  } catch {}
  return (await saved()) ?? fetch(url);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;
  const path = url.pathname.slice(new URL(self.registration.scope).pathname.length);
  if (request.mode !== "navigate") {
    const saved = () => caches.match(request);
    if (path.startsWith("static/soundfont/")) {
      event.respondWith((async () => {
        const kept = await saved();
        if (kept) return kept;
        const answer = await fetch(request);
        if (answer.ok) await (await caches.open(SOUNDS)).put(request, answer.clone());
        return answer;
      })());
      return;
    }
    event.respondWith(FRESH.has(path) ? freshOrSaved(request.url, saved) : (async () => (await saved()) ?? fetch(request))());
    return;
  }
  // Every page (?set=…, a tune's alaw/<folder>/) is the app, index.html. A tune's page
  // is folders down from it, so the saved copy points <base href> back up (../../).
  const up = "../".repeat(path.split("/").length - 1);
  event.respondWith(freshOrSaved(request.url, async () => {
    const app = await caches.match("./", { ignoreSearch: true });
    if (!app || !up) return app;
    const html = (await app.text()).replace('<base href="./">', `<base href="${up}">`);
    return new Response(html, { headers: app.headers });
  }));
});
