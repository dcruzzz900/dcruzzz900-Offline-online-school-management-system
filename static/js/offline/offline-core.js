/* My School Hub - offline core (V113).
   Environment-independent engine: a queue of pending changes, optional AES-GCM encryption, server reachability detection,
   and a sync engine that replays the queue against the real Flask routes. The browser wiring is at the bottom (SHOffline.boot);
   tests inject an in-memory store and a fake fetch (tests/js/offline_core_test.js).

   Safety rules the engine enforces:
   - a replay only counts as done when the server acknowledges THAT change id (X-Sync-Ack); a redirect to a login or error page is not success;
   - changes belong to the user who made them and are only replayed while that same user is signed in;
   - network errors / 5xx / 429 are retried with back-off; 4xx rule failures are shown as Failed (with the server's message) and never silently dropped;
   - an edit of a record that is still queued replaces the earlier queued edit but keeps the ORIGINAL base version, so conflict detection stays correct. */
(function (root) {
  "use strict";

  var MAX_AUTO_ATTEMPTS = 8, MAX_FILE_BYTES = 5 * 1024 * 1024, PING_TIMEOUT = 4000;
  var BACKOFF = [2000, 5000, 15000, 30000, 60000, 120000, 300000, 600000];
  var NEVER_QUEUE = /^\/(login|logout|account\/|platform|billing|ai\/|register|recover|activate|api\/(?!scores\/)|student\/logout|parent\/logout)/;
  var JSON_WRITE = /^\/api\/scores\//;

  function uuid(env) {
    if (env.uuid) return env.uuid();
    var c = root.crypto; if (c && c.randomUUID) return c.randomUUID();
    var b = new Uint8Array(16); (c || {}).getRandomValues ? c.getRandomValues(b) : b.forEach(function (_, i) { b[i] = Math.random() * 256; });
    return Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  function b64(buf) { var s = "", u = new Uint8Array(buf); for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]); return btoa(s); }
  function unb64(str) { var s = atob(str), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }

  /* ---------- encryption (AES-GCM, non-extractable key kept in IndexedDB; only where WebCrypto exists) ---------- */
  function makeCrypto(subtle, store) {
    if (!subtle) return { enabled: false, enc: async function (t) { return t; }, dec: async function (t) { return t; }, encBuf: async function (b) { return b; }, decBuf: async function (b) { return b; } };
    var keyP = null;
    function key() {
      if (!keyP) keyP = (async function () {
        var k = await store.keyGet();
        if (!k) { k = await subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]); await store.keyPut(k); }
        return k;
      })();
      return keyP;
    }
    async function encBuf(buf) {
      var iv = (root.crypto || globalThis.crypto).getRandomValues(new Uint8Array(12));
      var ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv: iv }, await key(), buf));
      var out = new Uint8Array(12 + ct.length); out.set(iv, 0); out.set(ct, 12); return out.buffer;
    }
    async function decBuf(buf) {
      var u = new Uint8Array(buf);
      return subtle.decrypt({ name: "AES-GCM", iv: u.slice(0, 12) }, await key(), u.slice(12));
    }
    return {
      enabled: true, encBuf: encBuf, decBuf: decBuf,
      enc: async function (t) { return b64(await encBuf(new TextEncoder().encode(t))); },
      dec: async function (t) { return new TextDecoder().decode(await decBuf(unb64(t))); }
    };
  }

  /* ---------- in-memory store (tests, and the fallback when IndexedDB is unavailable) ---------- */
  function memoryStore() {
    var q = {}, meta = {}, key = null;
    return {
      all: async function () { return Object.keys(q).map(function (k) { return q[k]; }).sort(function (a, b) { return a.seq - b.seq; }); },
      put: async function (e) { q[e.id] = JSON.parse(JSON.stringify(e, function (k, v) { return v instanceof ArrayBuffer ? { __ab: b64(v) } : v; }), function (k, v) { return v && v.__ab ? unb64(v.__ab).buffer : v; }); },
      del: async function (id) { delete q[id]; },
      metaGet: async function (k) { return meta[k]; }, metaSet: async function (k, v) { meta[k] = v; },
      keyGet: async function () { return key; }, keyPut: async function (k) { key = k; }
    };
  }

  /* ---------- IndexedDB store ---------- */
  function idbStore(idb) {
    var dbP = new Promise(function (res, rej) {
      var r = idb.open("sh-offline-v1", 1);
      r.onupgradeneeded = function () { var d = r.result; d.createObjectStore("queue", { keyPath: "id" }); d.createObjectStore("meta"); d.createObjectStore("keys"); };
      r.onsuccess = function () { res(r.result); }; r.onerror = function () { rej(r.error); };
    });
    function tx(store, mode, fn) {
      return dbP.then(function (db) { return new Promise(function (res, rej) {
        var t = db.transaction(store, mode), s = t.objectStore(store), out = fn(s);
        t.oncomplete = function () { res(out && out.result !== undefined ? out.result : undefined); }; t.onerror = t.onabort = function () { rej(t.error); };
      }); });
    }
    return {
      all: function () { return tx("queue", "readonly", function (s) { return s.getAll(); }).then(function (a) { return (a || []).sort(function (x, y) { return x.seq - y.seq; }); }); },
      put: function (e) { return tx("queue", "readwrite", function (s) { s.put(e); }); },
      del: function (id) { return tx("queue", "readwrite", function (s) { s.delete(id); }); },
      metaGet: function (k) { return tx("meta", "readonly", function (s) { return s.get(k); }); },
      metaSet: function (k, v) { return tx("meta", "readwrite", function (s) { s.put(v, k); }); },
      keyGet: function () { return tx("keys", "readonly", function (s) { return s.get("device"); }); },
      keyPut: function (k) { return tx("keys", "readwrite", function (s) { s.put(k, "device"); }); }
    };
  }

  /* ---------- the engine ---------- */
  function createCore(env) {
    var store = env.store, crypto = env.crypto, fetchFn = env.fetch, now = env.now || function () { return Date.now(); };
    var listeners = {}, running = false, seqCounter = 0, timer = null;
    var S = { status: "online", online: true, pending: 0, failed: 0, conflicts: 0, synced: 0, lastSync: null, progress: { done: 0, total: 0 }, error: "", fingerprint: "", deviceId: "", encrypted: !!crypto.enabled };

    function on(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); }
    function emit(ev, data) { (listeners[ev] || []).forEach(function (f) { try { f(data); } catch (e) {} }); }
    function setStatus(st, extra) { S.status = st; if (extra) Object.keys(extra).forEach(function (k) { S[k] = extra[k]; }); emit("status", snapshot()); }
    function snapshot() { return JSON.parse(JSON.stringify(S)); }

    async function refreshCounts() {
      var all = await store.all(), mine = all.filter(function (e) { return !S.fingerprint || e.userFp === S.fingerprint; });
      S.pending = mine.filter(function (e) { return e.state === "pending"; }).length;
      S.failed = mine.filter(function (e) { return e.state === "failed"; }).length;
      S.conflicts = mine.filter(function (e) { return e.state === "conflict"; }).length;
      S.otherUsers = all.length - mine.length;
      return all;
    }

    async function init() {
      S.deviceId = (await store.metaGet("deviceId")) || (function () { var d = "dev-" + uuid(env).slice(0, 12); store.metaSet("deviceId", d); return d; })();
      S.lastSync = (await store.metaGet("lastSync")) || null;
      S.fingerprint = (await store.metaGet("fingerprint")) || "";
      await refreshCounts();
      return snapshot();
    }

    /* reachability of OUR server (what matters for syncing), not "the internet" in general */
    async function ping() {
      var ctl = env.AbortController ? new env.AbortController() : null, t = ctl ? setTimeout(function () { ctl.abort(); }, PING_TIMEOUT) : null;
      try {
        var r = await fetchFn("/api/sync/ping", { cache: "no-store", credentials: "omit", signal: ctl ? ctl.signal : undefined });
        if (r && r.ok && r.text) { try { await r.text(); } catch (x) {} }   // read the body so the connection is released
        return !!(r && r.ok);
      } catch (e) { return false; } finally { if (t) clearTimeout(t); }
    }

    async function checkConnection() {
      var up = await ping(), was = S.online;
      S.online = up;
      if (!up) { setStatus("offline", { error: "" }); return false; }
      if (!was || S.status === "offline") setStatus("online");
      return true;
    }

    async function sessionInfo() {
      var r = await fetchFn("/api/sync/session", { cache: "no-store", credentials: "same-origin" });
      if (!r.ok) throw new Error("session " + r.status);
      var j = await r.json();
      if (j.authenticated) {
        S.fingerprint = j.fingerprint; await store.metaSet("fingerprint", j.fingerprint);
        await store.metaSet("verifiedAt", now()); await store.metaSet("windowDays", j.offline_window_days || 7);
      }
      return j;
    }

    /* offline access is only allowed for a limited time after the last online verification */
    async function offlineAllowed() {
      var v = await store.metaGet("verifiedAt"), d = (await store.metaGet("windowDays")) || 7;
      if (!v) return false;
      return now() - v <= d * 86400000;
    }

    /* ---------- queue ---------- */
    function nextSeq() { seqCounter += 1; return now() * 1000 + (seqCounter % 1000); }

    async function enqueue(spec) {
      /* spec: {id?, method, url, kind:'json'|'form', body (object | array of [k,v]), files:[{field,name,type,buffer}], entityKey?, baseVersion?} */
      if (!S.fingerprint) S.fingerprint = (await store.metaGet("fingerprint")) || "";
      if (!S.fingerprint) throw new Error("Not signed in: nothing can be saved offline.");
      var totalFile = (spec.files || []).reduce(function (n, f) { return n + (f.buffer ? f.buffer.byteLength : 0); }, 0);
      if (totalFile > MAX_FILE_BYTES) throw new Error("Files saved offline are limited to 5 MB per change.");
      var all = await store.all(), prior = null;
      if (spec.entityKey) prior = all.filter(function (e) { return e.entityKey === spec.entityKey && e.state === "pending" && e.userFp === S.fingerprint; })[0] || null;
      var entry = {
        id: spec.id || (prior && prior.id) || uuid(env), seq: prior ? prior.seq : nextSeq(), userFp: S.fingerprint,
        method: spec.method || "POST", url: spec.url, kind: spec.kind || "json", entityKey: spec.entityKey || "",
        baseVersion: prior ? prior.baseVersion : (spec.baseVersion === undefined ? null : spec.baseVersion),
        capturedAt: prior ? prior.capturedAt : new Date(now()).toISOString(), state: "pending", attempts: 0, error: "", nextAt: 0,
        enc: !!crypto.enabled, label: spec.label || ""
      };
      entry.payload = await crypto.enc(JSON.stringify(spec.body === undefined ? null : spec.body));
      entry.files = [];
      for (var i = 0; i < (spec.files || []).length; i++) {
        var f = spec.files[i]; entry.files.push({ field: f.field, name: f.name, type: f.type, buf: await crypto.encBuf(f.buffer) });
      }
      if (prior) { entry.id = prior.id; }
      await store.put(entry);
      await refreshCounts();
      setStatus(S.online ? S.status : "offline");
      emit("queued", { id: entry.id });
      return entry;
    }

    async function listQueue() { return (await store.all()).map(function (e) { return { id: e.id, url: e.url, method: e.method, state: e.state, attempts: e.attempts, error: e.error, capturedAt: e.capturedAt, label: e.label, entityKey: e.entityKey, mine: e.userFp === S.fingerprint, files: e.files.length }; }); }

    async function remove(id) { await store.del(id); await refreshCounts(); emit("status", snapshot()); }
    async function retry(id) {
      var all = await store.all(), e = all.filter(function (x) { return x.id === id; })[0];
      if (e && e.state === "failed") { e.state = "pending"; e.attempts = 0; e.error = ""; e.nextAt = 0; await store.put(e); await refreshCounts(); }
      return syncNow({ manual: true });
    }

    async function buildRequest(e, csrf) {
      var body = JSON.parse(await crypto.dec(e.payload)), headers = {
        "X-CSRF-Token": csrf, "X-Change-Id": e.id, "X-Offline-Replay": "1", "X-Captured-At": e.capturedAt, "X-Device-Id": S.deviceId, "Accept": "application/json"
      };
      if (e.baseVersion !== null && e.baseVersion !== undefined) headers["X-Base-Version"] = e.baseVersion;
      var init = { method: e.method, headers: headers, credentials: "same-origin" };
      if (e.kind === "json") { headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
      else {
        var fd = new env.FormData(), seen = false;
        (body || []).forEach(function (kv) { if (kv[0] === "csrf_token") { fd.append("csrf_token", csrf); seen = true; } else fd.append(kv[0], kv[1]); });
        if (!seen) fd.append("csrf_token", csrf);
        for (var i = 0; i < e.files.length; i++) {
          var f = e.files[i], data = await crypto.decBuf(f.buf);
          fd.append(f.field, new env.Blob([data], { type: f.type }), f.name);
        }
        init.body = fd;
      }
      return init;
    }

    function permanent(status) { return status >= 400 && status < 500 && status !== 408 && status !== 429; }

    async function sendOne(e, csrf) {
      var r;
      try { r = await fetchFn(e.url, await buildRequest(e, csrf)); }
      catch (err) { return { kind: "retry", error: "Network error" }; }
      if (r.redirected && /\/login/.test(r.url || "")) return { kind: "retry", error: "Your session expired - sign in again to finish syncing" };
      var ack = r.headers && r.headers.get ? r.headers.get("X-Sync-Ack") : null;
      var j = {}; try { j = await r.clone().json(); } catch (x) {}
      if (r.status === 409 && ack === e.id && j.conflict) return { kind: "conflict", error: j.error || "Conflict: an administrator must review this change.", json: j };
      if (ack === e.id && r.ok) return { kind: "done", json: j };
      if (ack === e.id && permanent(r.status)) return { kind: "failed", error: j.error || ("The server rejected this change (" + r.status + ").") };
      if (!ack && r.ok) return { kind: "retry", error: "The server did not confirm this change (are you signed in?)" };
      if (permanent(r.status)) return { kind: "failed", error: j.error || ("The server rejected this change (" + r.status + ").") };
      return { kind: "retry", error: "Server busy or unavailable (" + r.status + ")" };
    }

    /* replay every pending change of the signed-in user, oldest first */
    async function syncNow(opts) {
      opts = opts || {};
      if (running) return snapshot();
      running = true;
      try {
        if (!(await checkConnection())) return snapshot();
        var info;
        try { info = await sessionInfo(); } catch (e) { setStatus("failed", { error: "Could not reach the server session." }); return snapshot(); }
        if (!info.authenticated) { setStatus("failed", { error: "Please sign in again to finish syncing. Your changes are safe on this device." }); return snapshot(); }
        var all = await refreshCounts();
        var due = all.filter(function (e) { return e.userFp === S.fingerprint && e.state === "pending" && (opts.manual || e.nextAt <= now()); });
        if (!due.length) { setStatus(S.failed || S.conflicts ? "failed" : "online", { error: S.failed ? "Some changes failed - see the Sync Center." : (S.conflicts ? "Some changes need administrator review." : "") }); return snapshot(); }
        var done = 0, okN = 0, failN = 0, confN = 0, retryN = 0;
        setStatus("syncing", { progress: { done: 0, total: due.length }, error: "" });
        for (var i = 0; i < due.length; i++) {
          var e = due[i], res = await sendOne(e, info.csrf);
          e.attempts += 1;
          if (res.kind === "done") {
            if (res.json && res.json.updated_at !== undefined && e.entityKey) await store.metaSet("ver:" + e.entityKey, res.json.updated_at);
            await store.del(e.id); okN += 1; S.synced += 1;
          } else if (res.kind === "conflict") { e.state = "conflict"; e.error = res.error; await store.put(e); confN += 1; }
          else if (res.kind === "failed") { e.state = "failed"; e.error = res.error; await store.put(e); failN += 1; }
          else {
            e.error = res.error;
            if (e.attempts >= MAX_AUTO_ATTEMPTS) { e.state = "failed"; e.error += " - gave up after " + e.attempts + " tries. Use Retry."; failN += 1; }
            else { e.nextAt = now() + BACKOFF[Math.min(e.attempts - 1, BACKOFF.length - 1)]; retryN += 1; }
            await store.put(e);
            if (res.error === "Network error") { break; }                 // the link dropped again: stop, keep order, try later
          }
          done += 1; S.progress = { done: done, total: due.length }; emit("status", snapshot());
        }
        await refreshCounts();
        var finished = !retryN && !failN && !confN;
        if (okN) { S.lastSync = new Date(now()).toISOString(); await store.metaSet("lastSync", S.lastSync); }
        setStatus(finished ? "completed" : "failed", { error: finished ? "" : (failN ? "Some changes failed - see the Sync Center." : (confN ? "Some changes need administrator review." : "Will retry automatically.")) });
        try { await fetchFn("/api/sync/report", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": info.csrf },
          body: JSON.stringify({ device_id: S.deviceId, synced: okN, failed: failN, conflicts: confN }) }); } catch (x) {}
        if (retryN) schedule();
        if (finished) { var t = setTimeout(function () { if (S.status === "completed") setStatus("online"); }, 5000); if (t && t.unref) t.unref(); }
        return snapshot();
      } finally { running = false; }
    }

    function schedule(ms) { if (timer) clearTimeout(timer); timer = setTimeout(function () { syncNow(); }, ms || 5000); if (timer && timer.unref) timer.unref(); }

    /* version bookkeeping for conflict detection */
    async function getVersion(key) { var v = await store.metaGet("ver:" + key); return v === undefined ? null : v; }
    async function setVersion(key, v) { await store.metaSet("ver:" + key, v); }
    async function hasPending(key) { return (await store.all()).some(function (e) { return e.entityKey === key && e.state === "pending"; }); }

    return { init: init, on: on, state: snapshot, ping: ping, checkConnection: checkConnection, sessionInfo: sessionInfo, offlineAllowed: offlineAllowed,
             enqueue: enqueue, listQueue: listQueue, remove: remove, retry: retry, syncNow: syncNow, schedule: schedule, refreshCounts: refreshCounts,
             getVersion: getVersion, setVersion: setVersion, hasPending: hasPending, _store: store };
  }

  /* ---------- browser wiring ---------- */
  function boot() {
    var win = root, store;
    try { store = idbStore(win.indexedDB); } catch (e) { store = memoryStore(); }
    var crypto = makeCrypto(win.crypto && win.crypto.subtle && win.isSecureContext ? win.crypto.subtle : null, store);
    var realFetch = win.fetch.bind(win);
    var core = createCore({ store: store, crypto: crypto, fetch: realFetch, FormData: win.FormData, Blob: win.Blob, AbortController: win.AbortController });
    core.ready = core.init();

    function sameOriginPath(u) { try { var x = new URL(u, win.location.href); return x.origin === win.location.origin ? x.pathname : null; } catch (e) { return null; } }

    /* JSON score saves: attach a change id; if the link is down (or drops), queue the very same change instead of losing it */
    function scoreEstimate(url, body) {
      try {
        var host = document.getElementById("scoreApp"); if (!host) return {};
        var boot = JSON.parse(host.getAttribute("data-config")), t = 0;
        boot.fields.forEach(function (f) { t += parseFloat(body[f.key]) || 0; }); t = Math.round(t * 100) / 100;
        var g = { grade: "-", remark: "-" };
        boot.bands.forEach(function (b) { if (t >= b.min_score && t <= b.max_score) g = { grade: b.grade, remark: b.remark }; });
        return { total: t, grade: g.grade, remark: g.remark };
      } catch (e) { return {}; }
    }
    function entityKeyFor(path, body) { return "score:" + path + ":" + (body && body.student_id); }

    win.fetch = function (input, init) {
      init = init || {};
      var method = String(init.method || (input && input.method) || "GET").toUpperCase();
      var path = typeof input === "string" ? sameOriginPath(input) : (input && input.url ? sameOriginPath(input.url) : null);
      if (method === "GET" || !path || !JSON_WRITE.test(path) || typeof init.body !== "string") return realFetch(input, init);
      var body; try { body = JSON.parse(init.body); } catch (e) { return realFetch(input, init); }
      var id = uuid({}), headers = Object.assign({}, init.headers || {}); headers["X-Change-Id"] = id;
      var key = entityKeyFor(path, body);
      function queueIt() {
        return core.getVersion(key).then(function (base) {
          return core.enqueue({ id: id, method: method, url: path, kind: "json", body: body, entityKey: key, baseVersion: base === null ? "" : base, label: "Score entry" });
        }).then(function () {
          var est = scoreEstimate(path, body);
          return new Response(JSON.stringify(Object.assign({ ok: true, queued: true, offline: true, student_id: body.student_id, saved_at: "saved offline - waiting to sync" }, est)),
            { status: 202, headers: { "Content-Type": "application/json" } });
        });
      }
      if (win.navigator.onLine === false || !core.state().online) return queueIt();
      return realFetch(input, Object.assign({}, init, { headers: headers })).then(function (r) {
        return r.clone().json().then(function (j) { if (r.ok && j && j.updated_at !== undefined) core.setVersion(key, j.updated_at); return r; }, function () { return r; });
      }, function (err) { if (err && err.name === "AbortError") throw err; return queueIt(); });
    };

    /* remember the version of each score row the grid shows (unless a change for that row is still waiting to sync) */
    core.seedScoreVersions = function () {
      var host = document.getElementById("scoreApp"); if (!host) return;
      try {
        var cfg = JSON.parse(host.getAttribute("data-config")), path = sameOriginPath(cfg.save_url);
        cfg.students.forEach(function (s) { var key = entityKeyFor(path, { student_id: s.id }); core.hasPending(key).then(function (p) { if (!p) core.setVersion(key, s.v || ""); }); });
      } catch (e) {}
    };
    core.canQueuePath = function (path) { return !NEVER_QUEUE.test(path); };
    return core;
  }

  var api = { createCore: createCore, memoryStore: memoryStore, makeCrypto: makeCrypto, boot: boot, NEVER_QUEUE: NEVER_QUEUE };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.SHOffline = api;
})(typeof window !== "undefined" ? window : globalThis);
