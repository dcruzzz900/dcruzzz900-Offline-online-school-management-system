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

  /* ---------- per-user encryption ----------
     Every person who signs in on a device gets their OWN random data key (AES-GCM). That key is stored only "wrapped" by a key
     derived from the person's password (PBKDF2). Nothing of theirs can be read until they sign in with their password:
       - sign in (online or offline)  -> the wrapped key is opened and kept as a NON-extractable key while they are signed in
       - sign out / idle lock         -> that key is deleted again; the wrapped copy and the encrypted data stay
     The same mechanism checks the password for offline sign-in (a wrong password cannot open the wrapped key).
     Where WebCrypto is missing (plain http on a LAN) nothing can be encrypted, so offline sign-in is refused. */
  function makeCrypto(subtle, store, opts) {
    opts = opts || {};
    var ITER = opts.iterations || 250000;
    if (!subtle) return { enabled: false, enc: async function (t) { return t; }, dec: async function (t) { return t; }, encBuf: async function (b) { return b; }, decBuf: async function (b) { return b; },
      enroll: async function () { return false; }, unlock: async function () { return false; }, lock: async function () {}, isUnlocked: async function () { return false; },
      findUser: async function () { return null; }, addAliases: async function () {}, removeUser: async function () {}, listUsers: async function () { return []; } };
    var rnd = function (n) { return (root.crypto || globalThis.crypto).getRandomValues(new Uint8Array(n)); };
    async function keyFor(fp, legacy) {
      var k = await store.keyGet(legacy ? "device" : "unlocked:" + fp);
      if (!k) throw new Error(legacy ? "Older offline data cannot be opened on this device." : "This device is locked. Enter your password to continue.");
      return k;
    }
    async function encBuf(buf, fp) {
      var iv = rnd(12), ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv: iv }, await keyFor(fp), buf));
      var out = new Uint8Array(12 + ct.length); out.set(iv, 0); out.set(ct, 12); return out.buffer;
    }
    async function decBuf(buf, fp, legacy) {
      var u = new Uint8Array(buf);
      return subtle.decrypt({ name: "AES-GCM", iv: u.slice(0, 12) }, await keyFor(fp, legacy), u.slice(12));
    }
    async function kek(password, salt, iter) {
      var base = await subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
      return subtle.deriveKey({ name: "PBKDF2", salt: salt, iterations: iter, hash: "SHA-256" }, base, { name: "AES-GCM", length: 256 }, false, ["wrapKey", "unwrapKey"]);
    }
    async function unlock(fp, password) {
      var rec = await store.userGet("user:" + fp); if (!rec) return false;
      try {
        var key = await subtle.unwrapKey("raw", unb64(rec.wrapped), await kek(password, unb64(rec.salt), rec.iter), { name: "AES-GCM", iv: unb64(rec.iv) },
          { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
        await store.keyPut("unlocked:" + fp, key); return true;
      } catch (e) { return false; }
    }
    async function enroll(fp, aliases, password) {
      var salt = rnd(16), iv = rnd(12), dek = await subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
      var wrapped = await subtle.wrapKey("raw", dek, await kek(password, salt, ITER), { name: "AES-GCM", iv: iv });
      await store.userPut("user:" + fp, { fp: fp, salt: b64(salt), iter: ITER, iv: b64(iv), wrapped: b64(wrapped), aliases: aliases.slice(), created: Date.now() });
      for (var i = 0; i < aliases.length; i++) await store.userPut("alias:" + aliases[i], fp);
      return unlock(fp, password);
    }
    return {
      enabled: true, encBuf: encBuf, decBuf: decBuf, enroll: enroll, unlock: unlock,
      enc: async function (t, fp) { return b64(await encBuf(new TextEncoder().encode(t), fp)); },
      dec: async function (t, fp, legacy) { return new TextDecoder().decode(await decBuf(unb64(t), fp, legacy)); },
      lock: async function (fp) { await store.keyDel("unlocked:" + fp); },
      isUnlocked: async function (fp) { return !!(fp && await store.keyGet("unlocked:" + fp)); },
      findUser: async function (alias) { var f = await store.userGet("alias:" + alias); return f || null; },
      addAliases: async function (fp, aliases) {
        var rec = await store.userGet("user:" + fp); if (!rec) return;
        for (var i = 0; i < aliases.length; i++) { if (rec.aliases.indexOf(aliases[i]) < 0) rec.aliases.push(aliases[i]); await store.userPut("alias:" + aliases[i], fp); }
        await store.userPut("user:" + fp, rec);
      },
      removeUser: async function (fp) {
        var rec = await store.userGet("user:" + fp);
        if (rec) for (var i = 0; i < rec.aliases.length; i++) await store.userDel("alias:" + rec.aliases[i]);
        await store.userDel("user:" + fp); await store.keyDel("unlocked:" + fp);
      },
      listUsers: async function () { return (await store.userAll()).filter(function (r) { return r && r.fp && r.wrapped; }).map(function (r) { return { fp: r.fp, aliases: r.aliases, created: r.created }; }); }
    };
  }

  /* ---------- in-memory store (tests, and the fallback when IndexedDB is unavailable) ---------- */
  function memoryStore() {
    var q = {}, meta = {}, keys = {}, users = {};
    return {
      all: async function () { return Object.keys(q).map(function (k) { return q[k]; }).sort(function (a, b) { return a.seq - b.seq; }); },
      put: async function (e) { q[e.id] = JSON.parse(JSON.stringify(e, function (k, v) { return v instanceof ArrayBuffer ? { __ab: b64(v) } : v; }), function (k, v) { return v && v.__ab ? unb64(v.__ab).buffer : v; }); },
      del: async function (id) { delete q[id]; },
      metaGet: async function (k) { return meta[k]; }, metaSet: async function (k, v) { meta[k] = v; },
      keyGet: async function (id) { return keys[id]; }, keyPut: async function (id, k) { keys[id] = k; }, keyDel: async function (id) { delete keys[id]; },
      userGet: async function (id) { return users[id] ? JSON.parse(JSON.stringify(users[id])) : (id.indexOf("alias:") === 0 ? undefined : undefined); },
      userPut: async function (id, v) { users[id] = JSON.parse(JSON.stringify(v)); }, userDel: async function (id) { delete users[id]; },
      userAll: async function () { return Object.keys(users).filter(function (k) { return k.indexOf("user:") === 0; }).map(function (k) { return JSON.parse(JSON.stringify(users[k])); }); }
    };
  }

  /* ---------- IndexedDB store (v2 adds the per-user records; v1 data is kept) ---------- */
  function idbStore(idb) {
    var dbP = new Promise(function (res, rej) {
      var r = idb.open("sh-offline-v1", 2);
      r.onupgradeneeded = function () {
        var d = r.result;
        if (!d.objectStoreNames.contains("queue")) d.createObjectStore("queue", { keyPath: "id" });
        ["meta", "keys", "users"].forEach(function (n) { if (!d.objectStoreNames.contains(n)) d.createObjectStore(n); });
      };
      r.onsuccess = function () { r.result.onversionchange = function () { r.result.close(); }; res(r.result); }; r.onerror = function () { rej(r.error); };
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
      keyGet: function (id) { return tx("keys", "readonly", function (s) { return s.get(id); }); },
      keyPut: function (id, k) { return tx("keys", "readwrite", function (s) { s.put(k, id); }); },
      keyDel: function (id) { return tx("keys", "readwrite", function (s) { s.delete(id); }); },
      userGet: function (id) { return tx("users", "readonly", function (s) { return s.get(id); }); },
      userPut: function (id, v) { return tx("users", "readwrite", function (s) { s.put(v, id); }); },
      userDel: function (id) { return tx("users", "readwrite", function (s) { s.delete(id); }); },
      userAll: function () { return tx("users", "readonly", function (s) { return s.getAll(); }); }
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

    /* the person using this page right now (the page tells us; each user has their own queue, cache and key) */
    async function setUser(fp) {
      S.fingerprint = fp || ""; await store.metaSet("fingerprint", S.fingerprint); await refreshCounts();
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
        await store.metaSet("verifiedAt:" + j.fingerprint, now()); await store.metaSet("windowDays", j.offline_window_days || 7);
      }
      return j;
    }

    /* offline access is only allowed for a limited time after that person's last online verification */
    async function offlineAllowed(fp) {
      fp = fp || S.fingerprint;
      var v = await store.metaGet("verifiedAt:" + fp), d = (await store.metaGet("windowDays")) || 7;
      if (!v) return false;
      return now() - v <= d * 86400000;
    }

    /* ---------- offline sign-in (password checked locally against the key wrapped on first online sign-in) ---------- */
    function aliasOf(identifier, school) { return String(identifier || "").trim().toLowerCase() + "|" + String(school || "").trim().toLowerCase(); }
    function waitText(ms) { var m = Math.ceil(ms / 60000); return m <= 1 ? "a minute" : m + " minutes"; }
    async function offlineLogin(identifier, school, password) {
      if (!crypto.enabled) return { ok: false, error: "Offline sign-in needs HTTPS or localhost on this device." };
      var alias = aliasOf(identifier, school), fail = (await store.metaGet("fail:" + alias)) || { n: 0, until: 0 };
      if (fail.until > now()) return { ok: false, error: "Too many attempts. Try again in " + waitText(fail.until - now()) + "." };
      var generic = { ok: false, error: "Wrong username or password, or this person has not signed in on this device while online yet." };
      var fp = await crypto.findUser(alias), ok = false;
      if (fp) ok = await crypto.unlock(fp, password);
      if (!ok) {
        fail.n += 1; if (fail.n >= 5) fail.until = now() + Math.min(900000, 30000 * Math.pow(2, fail.n - 5));
        await store.metaSet("fail:" + alias, fail); return generic;
      }
      if (!(await offlineAllowed(fp))) { await crypto.lock(fp); return { ok: false, error: "Offline access has expired for this account. Connect to the internet and sign in." }; }
      await store.metaSet("fail:" + alias, { n: 0, until: 0 });
      await setUser(fp); await store.metaSet("lastActive", now());
      return { ok: true, fingerprint: fp };
    }

    /* A person who signed in OFFLINE has no server session yet. With their password we sign them in to the server in the background
       (the normal /login form), so their waiting changes can be sent. */
    async function serverLogin(identifier, school, password) {
      var j0 = await (await fetchFn("/api/sync/session", { cache: "no-store", credentials: "same-origin" })).json();
      var fd = new env.FormData(); fd.append("csrf_token", j0.csrf); fd.append("username", identifier); fd.append("password", password); if (school) fd.append("school_code", school);
      try { await fetchFn("/login", { method: "POST", body: fd, credentials: "same-origin" }); } catch (e) { return false; }
      var j = await (await fetchFn("/api/sync/session", { cache: "no-store", credentials: "same-origin" })).json();
      return !!(j.authenticated && j.fingerprint === S.fingerprint);
    }

    /* enroll (first online sign-in on this device) or re-open (later online sign-ins) the person's encrypted storage */
    async function enrollOrUnlock(fp, aliases, password) {
      if (!crypto.enabled) return false;
      var rec = await store.userGet("user:" + fp);
      if (rec && await crypto.unlock(fp, password)) { await crypto.addAliases(fp, aliases); return true; }
      return crypto.enroll(fp, aliases, password);          // new person, or the password was changed since: start a fresh key
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
      entry.kid = "u";
      entry.payload = await crypto.enc(JSON.stringify(spec.body === undefined ? null : spec.body), S.fingerprint);
      entry.files = [];
      for (var i = 0; i < (spec.files || []).length; i++) {
        var f = spec.files[i]; entry.files.push({ field: f.field, name: f.name, type: f.type, buf: await crypto.encBuf(f.buffer, S.fingerprint) });
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
      var body = JSON.parse(await crypto.dec(e.payload, e.userFp, !e.kid)), headers = {
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
          var f = e.files[i], data = await crypto.decBuf(f.buf, e.userFp, !e.kid);
          fd.append(f.field, new env.Blob([data], { type: f.type }), f.name);
        }
        init.body = fd;
      }
      return init;
    }

    function permanent(status) { return status >= 400 && status < 500 && status !== 408 && status !== 429; }

    async function sendOne(e, csrf) {
      var r, init;
      try { init = await buildRequest(e, csrf); }
      catch (err) { return { kind: "failed", error: "This waiting change can no longer be opened on this device (the password was changed or the data is damaged). Discard it and enter it again." }; }
      try { r = await fetchFn(e.url, init); }
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
        if (!info.authenticated) { setStatus("failed", { needsLogin: true, error: "Enter your password to send your waiting changes. They are safe on this device." }); return snapshot(); }
        S.needsLogin = false;
        if (crypto.enabled && !(await crypto.isUnlocked(S.fingerprint))) { setStatus("failed", { error: "Enter your password to unlock this device so waiting changes can be sent." }); return snapshot(); }
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

    return { init: init, metaGet: function (k) { return store.metaGet(k); }, metaSet: function (k, v) { return store.metaSet(k, v); }, queueAll: function () { return store.all(); }, queueDelete: function (id) { return store.del(id); }, setUser: setUser, serverLogin: serverLogin, offlineLogin: offlineLogin, enrollOrUnlock: enrollOrUnlock, crypto: crypto, aliasOf: aliasOf, on: on, state: snapshot, ping: ping, checkConnection: checkConnection, sessionInfo: sessionInfo, offlineAllowed: offlineAllowed,
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
    /* Remember the version of each score row the grid shows, so a later offline edit can say "I changed version X".
       Online: the page is fresh, so it always wins (unless that row still has a change waiting to sync).
       Offline (page came from the prepared cache): only fill in rows we have no version for - a missing base version is what
       used to make every offline edit of an existing score look like a conflict. */
    core.seedScoreVersions = function (onlyIfAbsent) {
      var host = document.getElementById("scoreApp"); if (!host) return;
      try {
        var cfg = JSON.parse(host.getAttribute("data-config")), path = sameOriginPath(cfg.save_url);
        cfg.students.forEach(function (s) {
          var key = entityKeyFor(path, { student_id: s.id });
          core.hasPending(key).then(function (p) {
            if (p) return;
            return core.getVersion(key).then(function (cur) { if (!onlyIfAbsent || cur === null) return core.setVersion(key, s.v || ""); });
          });
        });
      } catch (e) {}
    };
    core.canQueuePath = function (path) { return !NEVER_QUEUE.test(path); };
    return core;
  }

  var api = { createCore: createCore, memoryStore: memoryStore, makeCrypto: makeCrypto, boot: boot, NEVER_QUEUE: NEVER_QUEUE };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.SHOffline = api;
})(typeof window !== "undefined" ? window : globalThis);
