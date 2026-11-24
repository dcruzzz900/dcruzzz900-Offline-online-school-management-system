/* My School Hub - offline-capable service worker (V113).
   - /static files and the app shell: cached, answered from the cache first, refreshed in the background.
   - Pages (navigations): network first; if the network is down or slow, the last copy the SAME signed-in user saw is shown.
     A page is only cached when the server tags it with X-SH-User and that tag matches the user the app told us is active,
     so one person's cached pages are never shown to another person on a shared device.
   - Writes are NOT handled here: the page scripts (static/js/offline/) keep a queue in IndexedDB and replay it.
   - Never cached: /api/, /login, /logout, /platform (Super Admin stays online-only), downloads and PDFs. */
const VERSION = 'v113';
const STATIC_CACHE = 'sh-static-' + VERSION;
const PAGE_CACHE = 'sh-pages-' + VERSION;
const META_CACHE = 'sh-meta';
const USER_KEY = '/__sh_active_user';
const NAV_TIMEOUT_MS = 4000;
const SHELL = [
  '/offline', '/manifest.json',
  '/static/icons/icon-192.png?v=3', '/static/icons/icon-512.png?v=3',
  '/static/css/modern.css', '/static/css/modern-compat.css', '/static/css/theme.css', '/static/css/responsive-ui.css',
  '/static/js/offline/offline-core.js', '/static/js/offline/offline-ui.js',
  '/static/js/shell-ui.js', '/static/js/modern-shell.js', '/static/js/theme-toggle.js', '/static/js/top-search.js',
  '/static/js/floating-settings.js', '/static/js/password-toggle.js', '/static/js/table-filter.js',
  '/static/js/react-ui/lib.js', '/static/js/react-ui/forms.js', '/static/js/react-ui/score-entry.js'
];
// Third-party files are fetched in the background (never awaited), so a slow or blocked CDN cannot delay installation.
const EXTERNAL = ['https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js', 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css'];
const NEVER_CACHE = /^\/(api\/|login|logout|platform|student\/logout|parent\/logout|service-worker\.js)/;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    // one missing file must not fail the whole install
    await Promise.all(SHELL.map(async (u) => {
      try {
        const req = u.startsWith('http') ? new Request(u, { mode: 'no-cors' }) : new Request(u, { credentials: 'same-origin' });
        const res = await fetch(req);
        if (res && (res.ok || res.type === 'opaque')) await cache.put(u, res);
      } catch (e) { /* offline during install: skipped, filled in by runtime caching */ }
    }));
    EXTERNAL.forEach((u) => { fetchT(new Request(u, { mode: 'no-cors' }), 5000).then((r) => cache.put(u, r)).catch(() => {}); });
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => (k.startsWith('sh-static-') && k !== STATIC_CACHE) || (k.startsWith('sh-pages-') && k !== PAGE_CACHE)
      || !k.startsWith('sh-')).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

async function activeUser() {
  try { const r = await (await caches.open(META_CACHE)).match(USER_KEY); return r ? (await r.text()) : ''; } catch (e) { return ''; }
}
async function setActiveUser(fp) {
  const c = await caches.open(META_CACHE);
  if (fp) await c.put(USER_KEY, new Response(fp)); else await c.delete(USER_KEY);
}
async function purgePages() { await caches.delete(PAGE_CACHE); }

self.addEventListener('message', (event) => {
  const d = event.data || {};
  event.waitUntil((async () => {
    if (d.type === 'SET_USER') {
      const prev = await activeUser();
      if (prev && prev !== d.fingerprint) await purgePages();      // a different person: forget the previous person's pages
      await setActiveUser(d.fingerprint || '');
    } else if (d.type === 'PURGE_PAGES') {
      await purgePages(); await setActiveUser('');
    } else if (d.type === 'PREPARE' && Array.isArray(d.urls)) {
      await prepare(d.urls, d.fingerprint || '');
    } else if (d.type === 'WARM' && Array.isArray(d.urls)) {
      const cache = await caches.open(PAGE_CACHE);
      const user = await activeUser();
      for (const u of d.urls.slice(0, 40)) {
        try {
          const res = await fetch(u, { credentials: 'same-origin' });
          if (res.ok && !res.redirected && user && res.headers.get('X-SH-User') === user) await cache.put(u, res.clone());
        } catch (e) { /* offline: skip */ }
      }
    }
  })());
});

// fetch that gives up (and releases the connection) after ms, so a blocked host never leaves requests hanging
function fetchT(req, ms, opts) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  return fetch(req, Object.assign({ signal: ctl.signal }, opts || {})).finally(() => clearTimeout(t));
}
/* ---- PREPARE: right after login, download every page the user needs offline, without the user clicking anything.
   Starts from the menu pages, follows their links one level (class lists, score-entry pages, roll calls, ...) and also stores
   the CSS/JS those pages use. Pages are rendered per user by the server, so each role gets exactly its own pages.
   Links that look like actions (delete, approve, export, logout ...) are never fetched. */
const SKIP_LINK = /(logout|delete|remove|approve|publish|activate|reset|export|download|print|backup|restore|impersonate|toggle|lock|send|clear|purge|\.(pdf|xlsx?|csv|zip|docx?)(\?|$))/i;
const BLOCK_PATH = /^\/(api\/|login|logout|platform|static\/|student\/|parent\/|school-logo|manifest|service-worker)/;
const MAX_PAGES = 150, CONCURRENCY = 4;
async function broadcast(msg) { for (const c of await self.clients.matchAll({ includeUncontrolled: true })) c.postMessage(msg); }
async function prepare(seed, fp) {
  const prev = await activeUser();
  if (prev && prev !== fp) await purgePages();
  await setActiveUser(fp);
  const pages = await caches.open(PAGE_CACHE), stat = await caches.open(STATIC_CACHE);
  const norm = (u) => { try { const x = new URL(u, self.location.origin); return x.origin === self.location.origin ? x.pathname + x.search : null; } catch (e) { return null; } };
  const todo = [], seen = new Set(), assets = new Set();
  const add = (u, depth) => { const n = norm(u); if (n && !seen.has(n) && seen.size < MAX_PAGES && !BLOCK_PATH.test(n)) { seen.add(n); todo.push({ u: n, depth }); } };
  seed.forEach((u) => { const n = norm(u); if (n && !seen.has(n) && !BLOCK_PATH.test(n)) { seen.add(n); todo.push({ u: n, depth: 0 }); } });
  let done = 0, cached = 0, failed = 0, last = 0;
  async function worker() {
    for (let job; (job = todo.shift());) {
      try {
        const res = await fetchT(job.u, 20000, { credentials: 'same-origin' });
        if (res.ok && !res.redirected && res.headers.get('X-SH-User') === fp) {
          await pages.put(job.u, res.clone()); cached++;
          const html = await res.text();
          for (const m of html.matchAll(/(?:href|src)="([^"#]+)"/g)) {
            const h = m[1];
            if (/^\/static\//.test(h) || /^https:\/\/(cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)\//.test(h)) assets.add(h);
            else if (job.depth < 1 && h.startsWith('/') && !h.startsWith('//') && !SKIP_LINK.test(h)) add(h, job.depth + 1);
          }
        } else failed++;
      } catch (e) { failed++; }
      done++;
      if (Date.now() - last > 250) { last = Date.now(); await broadcast({ type: 'PREPARE_PROGRESS', done, total: done + todo.length }); }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  const list = [...assets];
  for (let i = 0; i < list.length; i += 6) {
    await Promise.all(list.slice(i, i + 6).map(async (a) => {
      try {
        if (await stat.match(a)) return;
        const r = await fetchT(a.startsWith('http') ? new Request(a, { mode: 'no-cors' }) : a, 8000);
        if (r && (r.ok || r.type === 'opaque')) await stat.put(a, r);
      } catch (e) { /* offline or blocked host: runtime caching fills it in later */ }
    }));
  }
  await broadcast({ type: 'PREPARE_DONE', cached, failed, assets: list.length });
}

function timeout(ms) { return new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)); }

async function handleNavigation(request) {
  const url = new URL(request.url);
  const cacheable = !NEVER_CACHE.test(url.pathname);
  const cache = await caches.open(PAGE_CACHE);
  try {
    const res = await Promise.race([fetch(request), timeout(NAV_TIMEOUT_MS)]);
    if (cacheable && res.ok && !res.redirected) {
      const tag = res.headers.get('X-SH-User'), user = await activeUser();
      if (tag && user && tag === user) await cache.put(url.pathname + url.search, res.clone());
    }
    return res;
  } catch (err) {
    if (cacheable) {
      const hit = await cache.match(url.pathname + url.search);
      if (hit) return hit;
    }
    const shell = await (await caches.open(STATIC_CACHE)).match('/offline');
    return shell || new Response('You are offline.', { status: 503, headers: { 'Content-Type': 'text/plain' } });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const hit = await cache.match(request, { ignoreVary: true });
  const net = fetchT(request, new URL(request.url).origin === self.location.origin ? 15000 : 3000).then((res) => { if (res && (res.ok || res.type === 'opaque')) cache.put(request, res.clone()); return res; }).catch(() => null);
  if (hit) return hit;
  // Nothing cached: wait for the network, but never hang a page on a slow/blocked third-party host.
  const res = await Promise.race([net, new Promise((r) => setTimeout(() => r(null), new URL(request.url).origin === self.location.origin ? 15000 : 2500))]);
  return res || new Response('', { status: 504 });
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate') { event.respondWith(handleNavigation(req)); return; }
  if (url.origin === self.location.origin) {
    if (url.pathname === '/offline' || url.pathname === '/manifest.json' || url.pathname.startsWith('/static/')) { event.respondWith(staleWhileRevalidate(req)); }
    return;                                               // everything else (JSON, downloads, uploads): normal network handling
  }
  if (/^https:\/\/(cdn\.jsdelivr\.net|fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com)\//.test(req.url)) {
    event.respondWith(staleWhileRevalidate(req));
  }
});
