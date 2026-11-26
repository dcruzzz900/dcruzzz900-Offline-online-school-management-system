/* My School Hub - offline UI (V113): registers the service worker, shows Online / Offline / Synchronizing / Sync Completed /
   Sync Failed, queues form submissions made while offline, protects against losing queued work at logout, and drives the
   "this device" panel of the Sync Center. Needs offline-core.js (loaded first). */
(function () {
  "use strict";
  if (!window.SHOffline) return;
  var core = SHOffline.boot();
  window.shOffline = core;
  var OFFLINE_VERSION = "v117";            // bump when the set of prepared pages changes: everyone prepares once more after an upgrade
  var REFRESH_MS = 60 * 60 * 1000;         // V117: the prepared pages are refreshed in the background whenever they are older than this and the school server is reachable
  var meta = document.querySelector('meta[name="sh-user"]');
  var fingerprint = meta ? meta.getAttribute("content") : "";
  var signedIn = !!fingerprint;
  /* Sign-in page: remember what was typed for ONE page load so the next page can set up this person's encrypted offline storage
     (their password is only needed once per device; it is never sent anywhere else and is removed as soon as it has been used). */
  var loginForm = document.getElementById("unifiedLoginForm");
  if (loginForm) {
    try { sessionStorage.removeItem("sh-login"); } catch (e) {}
    loginForm.addEventListener("submit", function () {
      try { sessionStorage.setItem("sh-login", JSON.stringify({ u: loginForm.elements.username.value, s: loginForm.elements.school_code ? loginForm.elements.school_code.value : "", p: loginForm.elements.password.value, t: Date.now() })); } catch (e) {}
    });
  }
  function takeHandoff() {
    try { var raw = sessionStorage.getItem("sh-login"); sessionStorage.removeItem("sh-login"); var h = raw && JSON.parse(raw); return h && Date.now() - h.t < 120000 ? h : null; } catch (e) { return null; }
  }
  var LABEL = { online: "Online", offline: "Offline", syncing: "Synchronizing…", completed: "Sync Completed", failed: "Sync Failed" };

  /* ---------- service worker ---------- */
  function swSend(msg) {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.ready.then(function (reg) { if (reg.active) reg.active.postMessage(msg); }).catch(function () {});
  }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(function () {});
  }

  /* ---------- connection indicator in the header: green Online / red Offline ---------- */
  var prep = { state: "idle", done: 0, total: 0 };       // idle | working | ready | unsupported
  var chip;
  function ensureChip() {
    chip = chip || document.getElementById("shConn");
    if (!chip && signedIn) {                                // pages without the header slot: small floating chip
      chip = document.createElement("a"); chip.id = "shConn"; chip.className = "sh-conn no-print"; chip.href = "/sync";
      chip.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:9990";
      chip.innerHTML = "<i></i><span class='sh-conn-text'></span><small class='sh-conn-sub'></small>"; document.body.appendChild(chip);
    }
    return chip;
  }
  function render(s) {
    ensureChip(); if (!chip) return;                       // V117: every header has the chip (student, parent, Super Admin too), signed in for offline use or not
    var st = s.status, text = LABEL[st] || "Online";
    if (st === "syncing" && s.progress && s.progress.total) text += " " + s.progress.done + "/" + s.progress.total;
    var sub = [];
    if (s.pending && st !== "syncing") sub.push(s.pending + " pending");
    if (s.conflicts) sub.push(s.conflicts + " need review");
    chip.setAttribute("data-state", st);
    chip.querySelector(".sh-conn-text").textContent = text;
    chip.querySelector(".sh-conn-sub").textContent = sub.length ? "· " + sub.join(" · ") : "";
    chip.title = (s.error || (s.online ? "Connected to the school server" : "No connection to the school server")) + (prep.state === "unsupported" ? " — offline pages need HTTPS or localhost" : "") + " | Last sync: " + (s.lastSync ? new Date(s.lastSync).toLocaleString() : "never");
    document.documentElement.setAttribute("data-sh-connection", s.online ? "online" : "offline");
    var sc = document.querySelector("[data-sync-center]"); if (sc) renderCenter(s);
  }
  /* a person who signed in offline has no server session yet: ask for the password once to send their waiting changes */
  var loginPrompt = false;
  function promptServerLogin() {
    if (loginPrompt || !signedIn) return; loginPrompt = true;
    core.crypto.listUsers().then(function (us) {
      var me = us.filter(function (u) { return u.fp === fingerprint; })[0], parts = me ? (me.aliases[0] || "|").split("|") : ["", ""];
      var d = document.createElement("div"); d.className = "sh-prep no-print"; d.setAttribute("role", "dialog");
      d.innerHTML = "<div class='box'><h2 style='font-size:1.15rem'>You are back online</h2><p>Enter your password to send the changes you made offline.</p><input type='password' autocomplete='current-password' placeholder='Your password' style='width:100%;padding:10px;border-radius:10px;border:0;margin:6px 0'><div class='msg' style='min-height:1.4em;color:#ffb4b4'></div><button type='button' class='go'>Send my changes</button> <button type='button' class='later' style='background:#475569'>Later</button></div>";
      document.body.appendChild(d);
      var inp = d.querySelector("input"), msg = d.querySelector(".msg"); inp.focus();
      d.querySelector(".later").onclick = function () { d.remove(); setTimeout(function () { loginPrompt = false; }, 120000); };
      function go() {
        msg.textContent = "";
        core.serverLogin(parts[0], parts[1], inp.value).then(function (ok) {
          if (!ok) { msg.textContent = "Could not sign in. Check your password."; return; }
          d.remove(); loginPrompt = false; core.syncNow({ manual: true });
        }).catch(function () { msg.textContent = "Could not reach the server."; });
      }
      d.querySelector(".go").onclick = go; inp.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
    });
  }
  core.on("status", function (s) { if (s.needsLogin && s.online) promptServerLogin(); });
  core.on("status", render);

  /* ---------- connectivity + automatic sync ---------- */
  var wasOffline = false;
  function connectionTick() {
    return core.checkConnection().then(function (up) {
      if (up && (wasOffline || core.state().pending)) { var back = wasOffline; wasOffline = false; if (back) maybePrepare(false); return core.syncNow(); }
      if (!up) wasOffline = true;
    });
  }
  window.addEventListener("online", connectionTick);
  window.addEventListener("offline", function () { wasOffline = true; core.checkConnection(); });
  setInterval(connectionTick, 10000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) connectionTick(); });

  /* ---------- offline gate: access only for a limited time after the last online sign-in check ---------- */
  function gate() {
    if (!signedIn) return;
    core.offlineAllowed().then(function (ok) {
      if (ok || core.state().online) return;
      var d = document.createElement("div");
      d.style.cssText = "position:fixed;inset:0;z-index:100000;background:rgba(0,19,91,.96);color:#fff;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px";
      d.innerHTML = "<div style='max-width:380px'><h2>Offline access has expired</h2><p>For security, this device can only be used offline for a limited time after you last signed in with a connection. Connect to the internet and sign in again. Your unsynced changes stay safely on this device.</p></div>";
      document.body.appendChild(d);
    });
  }

  /* ---------- forms submitted while offline are queued instead of lost ---------- */
  function toast(msg) {
    var t = document.createElement("div"); t.className = "sh-offline-toast no-print"; t.setAttribute("role", "status"); t.textContent = msg;
    document.body.appendChild(t); setTimeout(function () { t.remove(); }, 6000);
  }
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!signedIn || !form || form.tagName !== "FORM" || ev.defaultPrevented) return;
    if (String(form.method).toLowerCase() !== "post" || form.hasAttribute("data-no-offline")) return;
    var action; try { action = new URL(form.getAttribute("action") || location.pathname, location.href); } catch (e) { return; }
    if (action.origin !== location.origin || !core.canQueuePath(action.pathname)) return; // login, billing, etc. need the server
    if (form.__shChecked) { form.__shChecked = false; return; }                           // second pass: the server answered, submit normally
    ev.preventDefault(); ev.stopImmediatePropagation();
    var submitter = ev.submitter;
    /* Never trust "the browser says online": confirm the school server answers right now, otherwise keep the data on this device. */
    (navigator.onLine === false ? Promise.resolve(false) : core.checkConnection()).then(function (up) {
      if (up) { form.__shChecked = true; if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit(); return; }
      var fd = new FormData(form), fields = [], files = [], jobs = [];
      fd.forEach(function (v, k) {
        if (v instanceof File) { if (v.size) jobs.push(v.arrayBuffer().then(function (buf) { files.push({ field: k, name: v.name, type: v.type, buffer: buf }); })); }
        else fields.push([k, v]);
      });
      if (submitter && submitter.name) fields.push([submitter.name, submitter.value]);
      return Promise.all(jobs).then(function () {
        return core.enqueue({ method: "POST", url: action.pathname + action.search, kind: "form", body: fields, files: files, label: (document.title || "Form"),
          entityKey: /\/roll-call$/.test(action.pathname) ? "attendance:" + action.pathname : "" });
      }).then(function () {
        toast("Saved on this device. It will be sent automatically when the connection returns.");
      });
    }).catch(function (err) { toast(err && err.message ? err.message : "This could not be saved offline."); });
  }, true);

  /* ---------- sign out / lock: the person's key is removed from this device; their encrypted pages and waiting changes stay ---------- */
  function lockNow(thenGo) {
    core.crypto.lock(fingerprint).then(function () {
      if (!("serviceWorker" in navigator)) return;
      return navigator.serviceWorker.ready.then(function (reg) {
        return new Promise(function (resolve) {
          var ch = new MessageChannel(); ch.port1.onmessage = function () { resolve(); }; setTimeout(resolve, 3000);
          if (reg.active) reg.active.postMessage({ type: "LOCK" }, [ch.port2]); else resolve();
        });
      });
    }).catch(function () {}).then(function () { if (thenGo) location.href = thenGo; });
  }
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href$="/logout"]');
    if (!a || !signedIn) return;
    var s = core.state(), n = s.pending + s.failed + s.conflicts;
    if (n && !window.confirm("You have " + n + " change(s) that have not reached the server. They stay safely (encrypted) on this device and will sync the next time you sign in with a connection. Sign out now?")) { ev.preventDefault(); return; }
    ev.preventDefault();
    lockNow(s.online ? a.href : "/offline");                  // offline: no server to tell; the offline sign-in page is shown
  }, true);

  /* ---------- offline idle lock: after 30 minutes without use while offline, the password is needed again ---------- */
  var IDLE_MS = 30 * 60 * 1000, lastTouch = 0;
  function touch() { var t = Date.now(); if (t - lastTouch > 20000) { lastTouch = t; try { localStorage.setItem("sh-last-active", String(t)); } catch (e) {} } }
  ["click", "keydown", "touchstart", "scroll"].forEach(function (n) { document.addEventListener(n, touch, { passive: true, capture: true }); });
  function idleExpired() { var t = 0; try { t = parseInt(localStorage.getItem("sh-last-active"), 10) || 0; } catch (e) {} return t && Date.now() - t > IDLE_MS; }
  setInterval(function () { if (signedIn && !core.state().online && idleExpired()) lockNow("/offline"); }, 60000);

  /* ---------- Sync Center: "this device" panel ---------- */
  function renderCenter(s) {
    var root = document.querySelector("[data-sync-center]"); if (!root) return;
    function set(k, v) { var el = root.querySelector('[data-k="' + k + '"]'); if (el) el.textContent = v; }
    set("status", LABEL[s.status] || s.status); set("connection", s.online ? "Connected to the school server" : "No connection to the school server");
    set("pending", s.pending); set("failed", s.failed); set("conflicts", s.conflicts); set("synced", s.synced);
    set("last", s.lastSync ? new Date(s.lastSync).toLocaleString() : "Never"); set("error", s.error || "None");
    set("enc", s.encrypted ? "Queued changes are encrypted on this device" : "This browser cannot encrypt local data (use HTTPS or localhost)");
    var bar = root.querySelector("[data-k=bar]"); if (bar) { var p = s.progress && s.progress.total ? Math.round(100 * s.progress.done / s.progress.total) : (s.status === "completed" ? 100 : 0); bar.style.width = p + "%"; bar.setAttribute("aria-valuenow", p); }
    var ub = root.querySelector("[data-k=users]");
    if (ub) core.crypto.listUsers().then(function (us) {
      ub.textContent = "";
      if (!us.length) { var r0 = document.createElement("tr"), c0 = document.createElement("td"); c0.colSpan = 3; c0.textContent = core.state().encrypted ? "Nobody yet." : "Offline sign-in is not available here (needs HTTPS or localhost)."; r0.appendChild(c0); ub.appendChild(r0); return; }
      us.forEach(function (u) {
        var tr = document.createElement("tr"), t1 = document.createElement("td"), t2 = document.createElement("td"), t3 = document.createElement("td");
        t1.textContent = (u.aliases[0] || "").split("|")[0] + (u.fp === fingerprint ? "  (you)" : ""); t2.textContent = new Date(u.created).toLocaleDateString();
        var b = document.createElement("button"); b.className = "btn btn-sm btn-outline-danger"; b.textContent = "Remove from this device";
        b.onclick = function () { removePerson(u); }; t3.appendChild(b); tr.appendChild(t1); tr.appendChild(t2); tr.appendChild(t3); ub.appendChild(tr);
      });
    });
    core.listQueue().then(function (rows) {
      var tb = root.querySelector("[data-k=queue]"); if (!tb) return;
      tb.textContent = "";
      if (!rows.length) { var tr0 = document.createElement("tr"), td0 = document.createElement("td"); td0.colSpan = 5; td0.textContent = "Nothing waiting on this device."; tr0.appendChild(td0); tb.appendChild(tr0); return; }
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        [r.label || r.url, new Date(r.capturedAt).toLocaleString(), r.mine ? r.state : "belongs to another user", r.error || ""].forEach(function (t) { var td = document.createElement("td"); td.textContent = t; tr.appendChild(td); });
        var td = document.createElement("td");
        if (r.mine && r.state === "failed") { var b = document.createElement("button"); b.className = "btn btn-sm btn-primary"; b.textContent = "Retry"; b.onclick = function () { core.retry(r.id); }; td.appendChild(b); td.appendChild(document.createTextNode(" ")); }
        if (r.mine && (r.state === "failed" || r.state === "conflict")) { var d = document.createElement("button"); d.className = "btn btn-sm btn-outline-danger"; d.textContent = "Discard"; d.onclick = function () { if (confirm("Discard this change? It will not be sent to the server.")) core.remove(r.id).then(function () { renderCenter(core.state()); }); }; td.appendChild(d); }
        tr.appendChild(td); tb.appendChild(tr);
      });
    });
  }
  function removePerson(u) {
    core.queueAll().then(function (all) {
      var mine = all.filter(function (e) { return e.userFp === u.fp; });
      if (!window.confirm("Remove " + (u.aliases[0] || "this person").split("|")[0] + " from this device? Their offline pages and " + mine.length + " unsent change(s) on this device will be deleted. They can sign in online again later to set it up again.")) return;
      return Promise.all(mine.map(function (e) { return core.queueDelete(e.id); })).then(function () { return core.crypto.removeUser(u.fp); })
        .then(function () { return core.metaSet("prepared:" + u.fp, ""); })
        .then(function () { swSend({ type: "PURGE_USER", fingerprint: u.fp }); if (u.fp === fingerprint) lockNow("/offline"); else { core.refreshCounts().then(function () { renderCenter(core.state()); }); } });
    });
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-refresh-offline]");
    if (b) { ev.preventDefault(); b.disabled = true; prepareOffline().then(function (ok) { b.disabled = false; toast(ok ? "Offline pages refreshed." : "Could not refresh offline pages right now."); }); }
  });
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-sync-now]");
    if (b) { ev.preventDefault(); core.syncNow({ manual: true }); }
  });
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-resolve]");
    if (!b) return;
    ev.preventDefault();
    var id = b.getAttribute("data-conflict"), choice = b.getAttribute("data-resolve");
    if (choice === "apply_offline" && !confirm("Use the score you typed offline? It replaces the value currently on the server and is recorded in the audit trail.")) return;
    core.sessionInfo().then(function (info) {
      return fetch("/api/sync/conflicts/" + id + "/resolve", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": info.csrf }, body: JSON.stringify({ resolution: choice }) });
    }).then(function (r) { return r.json(); }).then(function (j) { if (j.ok) location.reload(); else alert(j.error || "Could not resolve."); });
  });

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-resolve-all]");
    if (!b) return;
    ev.preventDefault();
    var choice = b.getAttribute("data-resolve-all");
    if (!confirm(choice === "apply_offline" ? "Use the scores you typed offline for ALL listed conflicts? They replace the values on the server and are recorded in the audit trail." : "Keep the server's scores for ALL listed conflicts? Your offline entries will be discarded.")) return;
    b.disabled = true;
    core.sessionInfo().then(function (info) {
      return fetch("/api/sync/conflicts/resolve-all", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": info.csrf }, body: JSON.stringify({ resolution: choice }) });
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.failed && j.failed.length) alert(j.resolved + " resolved. " + j.failed.length + " could not be applied:\n" + j.failed.map(function (f) { return (f.student || ("#" + f.id)) + ": " + f.error; }).join("\n"));
      location.reload();
    });
  });

  /* ---------- offline preparation: ONCE per person per device, silently, right after their first online sign-in ---------- */
  var swMsg = null;
  if ("serviceWorker" in navigator) navigator.serviceWorker.addEventListener("message", function (ev) { if (swMsg) swMsg(ev.data || {}); });
  function menuUrls() {
    var urls = {}; urls[location.pathname + location.search] = 1; urls["/dashboard"] = 1; urls["/sync"] = 1;
    document.querySelectorAll("a.nav-item[href], .mobile-tabs a[href], .app-sidebar a[href]").forEach(function (a) {
      try { var u = new URL(a.href); if (u.origin === location.origin && !/logout|^\/platform|^\/api\//.test(u.pathname)) urls[u.pathname + u.search] = 1; } catch (e) {}
    });
    return Object.keys(urls);
  }
  function prepareOffline() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) { prep.state = "unsupported"; render(core.state()); return Promise.resolve(false); }
    prep = { state: "working", done: 0, total: 0 };
    return new Promise(function (resolve) {
      var finished = false;
      function finish(ok) {
        if (finished) return; finished = true; swMsg = null;
        prep.state = ok ? "ready" : "idle";
        (ok ? core.metaSet("prepared:" + fingerprint, OFFLINE_VERSION).then(function () { return core.metaSet("preparedAt:" + fingerprint, Date.now()); }) : Promise.resolve()).then(function () { render(core.state()); resolve(ok); });
      }
      swMsg = function (m) {
        if (m.type === "PREPARE_PROGRESS") { prep.done = m.done; prep.total = m.total; }
        else if (m.type === "PREPARE_DONE") finish(m.cached > 0);
      };
      navigator.serviceWorker.ready.then(function (reg) {
        (navigator.serviceWorker.controller || reg.active).postMessage({ type: "PREPARE", fingerprint: fingerprint, urls: menuUrls() });
      }).catch(function () { finish(false); });
      setTimeout(function () { finish(false); }, 300000);
    });
  }
  window.shPrepareOffline = prepareOffline;
  /* V117: offline pages never wait for somebody to open them once. The set of pages is downloaded right after sign-in (see afterUnlocked) and
     then kept fresh: whenever the school server is reachable and the last download is older than REFRESH_MS (page start, connection
     coming back, and every 10 minutes while the page is open) it runs again silently, so new classes, students and subjects are
     available offline without visiting them. */
  function maybePrepare(force) {
    if (!signedIn || !core.state().online || prep.state === "working") return Promise.resolve(false);
    return Promise.all([core.metaGet("prepared:" + fingerprint), core.metaGet("preparedAt:" + fingerprint)]).then(function (r) {
      var stale = r[0] !== OFFLINE_VERSION || !r[1] || Date.now() - r[1] > REFRESH_MS;
      if (!force && !stale) { prep.state = "ready"; render(core.state()); return false; }
      return core.crypto.isUnlocked(fingerprint).then(function (ok) { return (core.crypto.enabled && !ok) ? false : prepareOffline(); });
    }).catch(function () { return false; });
  }
  window.shMaybePrepareOffline = maybePrepare;
  setInterval(function () { maybePrepare(false); }, 10 * 60 * 1000);

  /* ---------- unlock prompt: only when somebody is already signed in online but their offline storage is locked ---------- */
  function promptUnlock(info) {
    try { if (sessionStorage.getItem("sh-unlock-later")) return; } catch (e) {}
    var d = document.createElement("div"); d.className = "sh-prep no-print"; d.setAttribute("role", "dialog");
    d.innerHTML = "<div class='box'><h2 style='font-size:1.15rem'>Turn on offline mode on this device</h2><p>Enter your password once so your school data can be kept safely (encrypted) on this device and used without internet.</p><input type='password' autocomplete='current-password' placeholder='Your password' style='width:100%;padding:10px;border-radius:10px;border:0;margin:6px 0'><div class='msg' style='min-height:1.4em;color:#ffb4b4'></div><button type='button' class='go'>Turn on</button> <button type='button' class='later' style='background:#475569'>Not now</button></div>";
    document.body.appendChild(d);
    var inp = d.querySelector("input"), msg = d.querySelector(".msg"); inp.focus();
    d.querySelector(".later").onclick = function () { try { sessionStorage.setItem("sh-unlock-later", "1"); } catch (e) {} d.remove(); };
    function go() {
      msg.textContent = "";
      core.sessionInfo().then(function (i) {
        return fetch("/api/sync/verify-password", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": i.csrf }, body: JSON.stringify({ password: inp.value }) });
      }).then(function (r) { return r.json(); }).then(function (j) {
        if (!j.ok) { msg.textContent = j.error || "That password is not correct."; return; }
        return core.enrollOrUnlock(fingerprint, [core.aliasOf(info.username, "")], inp.value).then(function (ok) { if (ok) { d.remove(); afterUnlocked(); } else msg.textContent = "Could not unlock this device."; });
      }).catch(function () { msg.textContent = "Could not reach the server."; });
    }
    d.querySelector(".go").onclick = go; inp.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
  }

  function afterUnlocked() {
    swSend({ type: "SET_USER", fingerprint: fingerprint });
    core.seedScoreVersions(false);
    if (core.state().pending) core.syncNow();
    maybePrepare(false);                                       // first time for this person on this device, after an upgrade, or when the saved pages are getting old
  }

  /* ---------- start ---------- */
  core.ready.then(function () {
    render(core.state());
    if (!signedIn) { core.checkConnection(); return; }          // student / parent / Super Admin / sign-in page: the chip still shows Online / Offline
    core.setUser(fingerprint).then(function () {
      core.seedScoreVersions(true);                                         // also when this page came from the offline cache
      var handoff = takeHandoff();
      return core.checkConnection().then(function (up) {
        if (!up) {
          wasOffline = true; swSend({ type: "SET_USER", fingerprint: fingerprint });
          if (idleExpired()) { lockNow("/offline"); return; }
          gate(); return;
        }
        return core.sessionInfo().then(function (info) {
          if (!info.authenticated) return;
          var aliases = handoff ? [core.aliasOf(handoff.u, handoff.s), core.aliasOf(info.username, handoff.s)] : [];
          var step = handoff ? core.enrollOrUnlock(fingerprint, aliases, handoff.p) : Promise.resolve();
          return step.then(function () { return core.crypto.enabled ? core.crypto.isUnlocked(fingerprint) : true; }).then(function (ok) {
            if (core.crypto.enabled && !ok) { swSend({ type: "SET_USER", fingerprint: fingerprint }); promptUnlock(info); return; }
            afterUnlocked();
          });
        });
      });
    }).catch(function () {});
  });
})();
