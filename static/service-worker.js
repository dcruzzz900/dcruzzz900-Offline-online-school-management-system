/* My School Hub - offline service worker (V114).
   Several people can use one device, online or offline:
   - every person has their OWN page cache (sh-pages-<version>-<user>), and every cached page is stored ENCRYPTED with that
     person's key. The key only exists in this browser while that person is signed in (it is opened with their password), so
     pages of a person who is signed out - or of anybody else - cannot be read from the device;
   - /static files and the shell are shared (they hold no school data) and answered from the cache first;
   - page navigations: network first; if the network is down or slow, the signed-in person's last copy is decrypted and shown;
     with nobody signed in (locked) the offline sign-in page is shown instead;
   - writes are NOT handled here: the page scripts keep a queue in IndexedDB (encrypted per person) and replay it.
   Never cached: /api/, /login, /logout, /platform (Super Admin stays online-only). */
const VERSION = 'v114';
const STATIC_CACHE = 'sh-static-' + VERSION;
const PAGE_PREFIX = 'sh-pages-' + VERSION + '-';
const META_CACHE = 'sh-meta';
const USER_KEY = '/__sh_active_user';
const NAV_TIMEOUT_MS = 4000;
const SHELL = [
  '/offline', '/manifest.json',
  '/static/icons/icon-192.png?v=3', '/static/icons/icon-512.png?v=3',
  '/static/css/modern.css', '/static/css/modern-compat.css', '/static/css/theme.css', '/static/css/responsive-ui.css', '/static/css/offline.css',
  '/static/js/offline/offline-core.js', '/static/js/offline/offline-ui.js', '/static/js/offline/offline-login.js',
  '/static/js/shell-ui.js', '/static/js/modern-shell.js', '/static/js/theme-toggle.js', '/static/js/top-search.js',
  '/static/js/floating-settings.js', '/static/js/password-toggle.js', '/static/js/table-filter.js',
  '/static/js/react-ui/lib.js', '/static/js/react-ui/forms.js', '/static/js/react-ui/score-entry.js'
];
// Third-party files are fetched in the background (never awaited), so a slow or blocked CDN cannot delay installation.
const EXTERNAL = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js',
  'https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js'
];
const NEVER_CACHE = /^\/(api\/|login|logout|platform|student\/logout|parent\/logout|service-worker\.js)/;
const EXTERNAL_HOSTS = /^https:\/\/(cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com|fonts\.googleapis\.com|fonts\.gstatic\.com)\//;

// fetch that gives up (and releases the connection) after ms, so a blocked host never leaves requests hanging
function fetchT(req, ms, opts) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  return fetch(req, Object.assign({ signal: ctl.signal }, opts || {})).finally(() => clearTimeout(t));
}
function timeout(ms) { return new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)); }
// Third-party assets are fetched in CORS mode (the pages ask for them with crossorigin="anonymous"); no-cors only as a fallback
async function fetchExternal(u, ms) {
  try { const r = await fetchT(new Request(u, { mode: 'cors', credentials: 'omit' }), ms); if (r.ok) return r; } catch (e) { /* fall through */ }
  const r = await fetchT(new Request(u, { mode: 'no-cors' }), ms); return r.type === 'opaque' ? r : null;
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.all(SHELL.map(async (u) => {                // one missing file must not fail the whole install
      try { const res = await fetch(new Request(u, { credentials: 'same-origin' })); if (res && res.ok) await cache.put(u, res); } catch (e) { /* filled in later */ }
    }));
    EXTERNAL.forEach((u) => { fetchExternal(u, 8000).then((r) => r && cache.put(u, r)).catch(() => {}); });
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // drop caches of older worker versions (and pre-V114 caches); NEVER touch other people's current page caches
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => (k.startsWith('sh-static-') && k !== STATIC_CACHE) || (k.startsWith('sh-pages-') && !k.startsWith(PAGE_PREFIX))
      || !k.startsWith('sh-')).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

/* ---- who is signed in right now on this device ---- */
async function activeUser() {
  try { const r = await (await caches.open(META_CACHE)).match(USER_KEY); return r ? (await r.text()) : ''; } catch (e) { return ''; }
}
async function setActiveUser(fp) {
  const c = await caches.open(META_CACHE);
  if (fp) await c.put(USER_KEY, new Response(fp)); else await c.delete(USER_KEY);
}

/* ---- the person's key lives in IndexedDB only while they are signed in (see offline-core.js) ---- */
function unlockedKey(fp) {
  return new Promise((resolve) => {
    if (!fp) return resolve(null);
    try {
      const r = indexedDB.open('sh-offline-v1');
      r.onerror = () => resolve(null);
      r.onsuccess = () => {
        const db = r.result; db.onversionchange = () => db.close();
        try {
          if (!db.objectStoreNames.contains('keys')) { db.close(); return resolve(null); }
          const g = db.transaction('keys').objectStore('keys').get('unlocked:' + fp);
          g.onsuccess = () => { db.close(); resolve(g.result || null); };
          g.onerror = () => { db.close(); resolve(null); };
        } catch (e) { db.close(); resolve(null); }
      };
    } catch (e) { resolve(null); }
  });
}
async function seal(res, key) {
  const buf = await res.clone().arrayBuffer(), iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, buf));
  const out = new Uint8Array(12 + ct.length); out.set(iv, 0); out.set(ct, 12);
  return new Response(out, { status: 200, headers: { 'Content-Type': 'application/octet-stream', 'X-SH-Enc': '1', 'X-SH-CT': res.headers.get('Content-Type') || 'text/html; charset=utf-8' } });
}
async function unseal(res, key) {
  const u = new Uint8Array(await res.arrayBuffer());
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: u.slice(0, 12) }, key, u.slice(12));
  return new Response(pt, { status: 200, headers: { 'Content-Type': res.headers.get('X-SH-CT') || 'text/html; charset=utf-8', 'X-SH-Offline': '1' } });
}
async function putPage(fp, key, path, res) { await (await caches.open(PAGE_PREFIX + fp)).put(path, await seal(res, key)); }
async function getPage(fp, key, path) {
  const hit = await (await caches.open(PAGE_PREFIX + fp)).match(path);
  if (!hit) return null;
  try { return await unseal(hit, key); } catch (e) { return null; }
}

self.addEventListener('message', (event) => {
  const d = event.data || {};
  event.waitUntil((async () => {
    if (d.type === 'SET_USER') await setActiveUser(d.fingerprint || '');                      // does NOT delete anyone's cache
    else if (d.type === 'LOCK') await setActiveUser('');                                        // signed out: cache stays, but is unreadable
    else if (d.type === 'PURGE_USER' && d.fingerprint) {                                        // "remove this person from this device"
      await caches.delete(PAGE_PREFIX + d.fingerprint);
      if ((await activeUser()) === d.fingerprint) await setActiveUser('');
    } else if (d.type === 'PREPARE' && Array.isArray(d.urls)) {
      if (event.ports && event.ports[0]) event.ports[0].postMessage({ ok: true });
      await prepare(d.urls, d.fingerprint || '');
      return;
    }
    if (event.ports && event.ports[0]) event.ports[0].postMessage({ ok: true });                // the page waits for this before it navigates
  })());
});

/* ---- PREPARE: the first time a person signs in on a device, download every page they need offline, silently.
   Starts from the menu pages and follows their links up to three levels (class lists -> score entry, roll calls, student pages ...),
   and stores the CSS/JS/fonts those pages use. Pages are rendered per user by the server, so each role gets exactly its own pages.
   Links that look like actions (delete, approve, export, logout ...) are never fetched. */
const SKIP_LINK = /(logout|delete|remove|approve|publish|activate|reset|export|download|print|backup|restore|impersonate|toggle|lock|send|clear|purge|\.(pdf|xlsx?|csv|zip|docx?)(\?|$))/i;
const BLOCK_PATH = /^\/(api\/|login|logout|platform|static\/|student\/|parent\/|school-logo|manifest|service-worker|offline)/;
const MAX_PAGES = 600, MAX_DEPTH = 3, CONCURRENCY = 6;
async function broadcast(msg) { for (const c of await self.clients.matchAll({ includeUncontrolled: true })) c.postMessage(msg); }

async function fetchAsset(a, stat) {
  if (await stat.match(a)) return;
  const ext = a.startsWith('http');
  try {
    const r = ext ? await fetchExternal(a, 10000) : await fetchT(a, 10000, { credentials: 'same-origin' });
    if (r && (r.ok || r.type === 'opaque')) {
      await stat.put(a, r.clone());
      if (/fonts\.googleapis\.com/.test(a) && r.ok) {                               // the font files named inside the stylesheet
        const css = await r.text();
        for (const m of css.matchAll(/url\((https:\/\/fonts\.gstatic\.com[^)]+)\)/g)) await fetchAsset(m[1], stat);
      }
    }
  } catch (e) { /* offline or blocked host: runtime caching fills it in later */ }
}

async function prepare(seed, fp) {
  const key = await unlockedKey(fp);
  if (!fp || !key) { await broadcast({ type: 'PREPARE_DONE', cached: 0, failed: 0, error: 'locked' }); return; }
  await setActiveUser(fp);
  const stat = await caches.open(STATIC_CACHE);
  const norm = (u) => { try { const x = new URL(u, self.location.origin); return x.origin === self.location.origin ? x.pathname + x.search : null; } catch (e) { return null; } };
  const todo = [], seen = new Set(), assets = new Set();
  const add = (u, depth) => { const n = norm(u); if (n && !seen.has(n) && seen.size < MAX_PAGES && !BLOCK_PATH.test(n)) { seen.add(n); todo.push({ u: n, depth }); } };
  seed.forEach((u) => add(u, 0));
  let done = 0, cached = 0, failed = 0, last = 0;
  async function worker() {
    for (let job; (job = todo.shift());) {
      try {
        const res = await fetchT(job.u, 20000, { credentials: 'same-origin' });
        if (res.ok && !res.redirected && res.headers.get('X-SH-User') === fp) {
          await putPage(fp, key, job.u, res.clone()); cached++;
          const html = await res.text();
          for (const m of html.matchAll(/(?:href|src)="([^"#]+)"/g)) {
            const h = m[1].replace(/&amp;/g, '&');
            if (/^\/static\//.test(h) || EXTERNAL_HOSTS.test(h)) assets.add(h);
            else if (job.depth < MAX_DEPTH && h.startsWith('/') && !h.startsWith('//') && !SKIP_LINK.test(h)) add(h, job.depth + 1);
          }
          for (const m of html.matchAll(/<link[^>]+href="(https:\/\/fonts\.googleapis\.com[^"]+)"/g)) assets.add(m[1].replace(/&amp;/g, '&'));
        } else failed++;
      } catch (e) { failed++; }
      done++;
      if (Date.now() - last > 250) { last = Date.now(); await broadcast({ type: 'PREPARE_PROGRESS', done, total: done + todo.length }); }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  const list = [...assets];
  for (let i = 0; i < list.length; i += 6) await Promise.all(list.slice(i, i + 6).map((a) => fetchAsset(a, stat)));
  await broadcast({ type: 'PREPARE_DONE', cached, failed, assets: list.length });
}

async function handleNavigation(request) {
  const url = new URL(request.url), path = url.pathname + url.search;
  const cacheable = !NEVER_CACHE.test(url.pathname);
  try {
    const res = await Promise.race([fetch(request), timeout(NAV_TIMEOUT_MS)]);
    if (cacheable && res.ok && !res.redirected) {
      const tag = res.headers.get('X-SH-User'), user = await activeUser();
      if (tag && user && tag === user) {
        const key = await unlockedKey(user);
        if (key) { try { await putPage(user, key, path, res.clone()); } catch (e) { /* quota etc.: ignore */ } }
      }
    }
    return res;
  } catch (err) {
    if (cacheable) {
      const user = await activeUser(), key = await unlockedKey(user);
      if (user && key) { const page = await getPage(user, key, path); if (page) return page; }
    }
    const shell = await (await caches.open(STATIC_CACHE)).match('/offline');
    return shell || new Response('You are offline.', { status: 503, headers: { 'Content-Type': 'text/plain' } });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const hit = await cache.match(request, { ignoreVary: true });
  const same = new URL(request.url).origin === self.location.origin;
  const net = fetchT(request, same ? 15000 : 3000).then((res) => { if (res && (res.ok || res.type === 'opaque')) cache.put(request, res.clone()); return res; }).catch(() => null);
  if (hit) return hit;
  const res = await Promise.race([net, new Promise((r) => setTimeout(() => r(null), same ? 15000 : 2500))]);   // never hang a page on a blocked host
  return res || new Response('', { status: 504 });
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate') { event.respondWith(handleNavigation(req)); return; }
  if (url.origin === self.location.origin) {
    if (url.pathname === '/offline' || url.pathname === '/manifest.json' || url.pathname.startsWith('/static/')) event.respondWith(staleWhileRevalidate(req));
    return;                                               // everything else (JSON, downloads, uploads): normal network handling
  }
  if (EXTERNAL_HOSTS.test(req.url)) event.respondWith(staleWhileRevalidate(req));
});
