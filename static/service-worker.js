const CACHE_NAME = "school-results-shell-v7";
const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  // The offline-first app shell and everything it needs to run are
  // precached explicitly here (not just cached-on-visit like other pages)
  // so a device that has enrolled for offline access (Settings → Offline
  // Access) but has never actually opened /offline-app yet still has it
  // available the very first time it loses connectivity.
  "/app",
  "/static/js/connectivity.js",
  "/static/js/offline-crypto.js",
  "/static/js/offline-db.js",
  "/static/js/offline-auth.js",
  "/static/js/sync-engine.js",
  "/static/js/offline-results.js",
  "/static/js/xlsx-lite.js",
  "/static/js/offline-materials.js",
  "/static/js/offline-app-ui.js",
];

// Downloaded learning materials live in caches named srs-materials-<schoolId>
// (see offline-materials.js). They are per school and must survive service
// worker updates, so they're exempt from the old-cache cleanup below.
const MATERIALS_PREFIX = "srs-materials-";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME && !k.startsWith(MATERIALS_PREFIX)).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Network-first for EVERYTHING, including static assets (css/icons). This
// app changes frequently, so we always want the latest CSS/JS/icons when
// the phone is online — the cache is only a fallback for when it's offline,
// not a way to skip fetching fresh files. (An earlier version of this file
// used cache-first for /static/, which caused phones to get stuck showing
// an old stylesheet indefinitely — this fixes that.)
//
// GET page responses (Score Entry, Roll Call, admin lists, etc.) are cached
// the same way static assets are, so a page that's been opened at least
// once while online can be reopened with zero connectivity — not just have
// its form submission queued by offline-queue.js. Only same-origin GET
// requests are ever cached; POSTs are left alone so a failed form
// submission surfaces as a normal network error to the caller instead of
// silently getting a cached page back as its "response". Non-HTML,
// non-static responses (generated PDFs, CSV/XLSX exports) are skipped too
// — a stale copy of those isn't useful offline and they can be large.
self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  const isStatic = url.pathname.startsWith("/static/");

  // The sync API and the connectivity check must reach the REAL network and fail
  // like the real network: answering them from a cache, or with a friendly "you're
  // offline" page, would make a dead connection look alive.
  if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") return;

  // Opening the app (its start page, "/", or the login page) with no working
  // connection goes straight to the offline app, which asks for the person's
  // password and then works from the data saved on the device. "?online=1"
  // opts out (the offline app's "log in online" link uses it, so a person who
  // really wants the online site isn't bounced back).
  if (req.mode === "navigate" && ENTRY_PATHS.has(url.pathname) && !url.searchParams.has("online")) {
    event.respondWith(openAppNavigation(req));
    return;
  }

  event.respondWith(networkFirst(req, isStatic));
});

// Network first, cache as the fallback. When a cached copy exists the network
// only gets a few seconds to start answering: on a weak connection where
// requests hang rather than fail, waiting forever would leave the app (and the
// offline app itself) stuck on a blank screen even though everything it needs is
// already on the device. With nothing cached there is nothing to fall back to, so
// the network gets longer. Only the wait for the FIRST response is limited — a
// download that has started is never cut off.
const CACHED_FALLBACK_TIMEOUT_MS = 4000;
const UNCACHED_TIMEOUT_MS = 30000;

async function networkFirst(req, isStatic) {
  const cached = await caches.match(req);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cached ? CACHED_FALLBACK_TIMEOUT_MS : UNCACHED_TIMEOUT_MS);
  try {
    const response = await fetch(req, { signal: controller.signal });
    clearTimeout(timer);
    const type = response.headers.get("Content-Type") || "";
    if (response.ok && (isStatic || type.includes("text/html"))) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
    }
    return response;
  } catch (err) {
    clearTimeout(timer);
    return cached || new Response(
      "<h2 style='font-family:sans-serif;padding:2rem;'>You're offline and this page hasn't been opened on this device before, so it isn't available yet. Open it once while connected, and it'll work offline after that.</h2>",
      { headers: { "Content-Type": "text/html" } });
  }
}

const ENTRY_PATHS = new Set(["/", "/dashboard", "/login"]);
// On a poor connection "online" can mean a request that just hangs. Rather than
// leave someone staring at a blank screen, give the network this long, then
// fall back to the offline app (which works the same and syncs later).
const ENTRY_TIMEOUT_MS = 8000;

async function openAppNavigation(req) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ENTRY_TIMEOUT_MS);
  try {
    const response = await fetch(req, { signal: controller.signal });
    clearTimeout(timer);
    const type = response.headers.get("Content-Type") || "";
    if (response.ok && type.includes("text/html")) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
    }
    return response;
  } catch (err) {
    clearTimeout(timer);
    if (await caches.match("/app")) {
      return Response.redirect(new URL("/app", self.location.origin).href, 302);
    }
    const cached = await caches.match(req);
    return cached || new Response(
      "<h2 style='font-family:sans-serif;padding:2rem;'>You're offline and the offline app hasn't been set up on this device yet. Connect to the internet and log in once to set it up.</h2>",
      { headers: { "Content-Type": "text/html" } });
  }
}

// Cached pages are stored per URL, not per person, so on a shared device one
// user's cached pages could otherwise be served to the next user (or the next
// school) when offline. The pages call this when someone logs out or a
// different user/school signs in.
//   purge-pages : forget every cached page (keeps the app shell files)
//   purge-all   : also forget saved learning materials (a different school signed in)
self.addEventListener("message", (event) => {
  const type = event.data && event.data.type;
  if (type !== "purge-pages" && type !== "purge-all") return;
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    const shell = new Set(SHELL_ASSETS);
    for (const req of await cache.keys()) {
      const path = new URL(req.url).pathname;
      if (!shell.has(path)) await cache.delete(req);
    }
    if (type === "purge-all") {
      for (const k of await caches.keys()) if (k.startsWith(MATERIALS_PREFIX)) await caches.delete(k);
      await cache.delete("/app");   // carries the previous school's name; refetched below
      try { await cache.add("/app"); } catch (e) { /* offline: it will be re-cached on next visit */ }
    }
  })());
});
