/* My School Hub — installable, but still ONLINE-ONLY.
   This worker exists so phones treat the site as an installable app. It caches nothing and never answers from a cache:
   every request goes to the server. When the server cannot be reached it shows a plain "no connection" page instead of
   a browser error. Any cache left by older offline builds is deleted on activation. */
const OFFLINE_PAGE = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>My School Hub</title>' +
  '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#00135b;color:#fff;font-family:Arial,Helvetica,sans-serif;text-align:center;padding:24px">' +
  '<div style="max-width:360px"><img src="/static/icons/icon-192.png?v=3" width="96" height="96" alt="" style="border-radius:22px"><h1 style="font-size:1.3rem;margin:16px 0 8px">My School Hub</h1>' +
  '<p style="line-height:1.5;color:#cfe0ff">Cannot reach the server. Check your internet connection. Nothing is saved until the connection returns.</p>' +
  '<button onclick="location.reload()" style="margin-top:12px;padding:12px 22px;border:0;border-radius:12px;background:#2f7bff;color:#fff;font-size:1rem;font-weight:700">Try again</button></div></body></html>';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try { const keys = await caches.keys(); await Promise.all(keys.map((k) => caches.delete(k))); } catch (e) {}
    try { await self.clients.claim(); } catch (e) {}
  })());
});
self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') { return; }          // everything except page loads: the browser's normal network handling
  event.respondWith(fetch(event.request).catch(() => new Response(OFFLINE_PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } })));
});
