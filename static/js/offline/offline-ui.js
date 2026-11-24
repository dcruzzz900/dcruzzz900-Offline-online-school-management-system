/* My School Hub - offline UI (V113): registers the service worker, shows Online / Offline / Synchronizing / Sync Completed /
   Sync Failed, queues form submissions made while offline, protects against losing queued work at logout, and drives the
   "this device" panel of the Sync Center. Needs offline-core.js (loaded first). */
(function () {
  "use strict";
  if (!window.SHOffline) return;
  var core = SHOffline.boot();
  window.shOffline = core;
  var meta = document.querySelector('meta[name="sh-user"]');
  var fingerprint = meta ? meta.getAttribute("content") : "";
  var signedIn = !!fingerprint;
  var LABEL = { online: "Online", offline: "Offline", syncing: "Synchronizing…", completed: "Sync Completed", failed: "Sync Failed" };

  /* ---------- service worker ---------- */
  function swSend(msg) {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.ready.then(function (reg) { if (reg.active) reg.active.postMessage(msg); }).catch(function () {});
  }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(function () {});
  }

  /* ---------- status pill ---------- */
  var pill;
  function ensurePill() {
    if (pill || !signedIn) return pill;
    pill = document.createElement("a");
    pill.id = "shSyncPill"; pill.href = "/sync"; pill.setAttribute("role", "status"); pill.setAttribute("aria-live", "polite");
    pill.className = "sh-sync-pill no-print";
    document.body.appendChild(pill);
    return pill;
  }
  function render(s) {
    if (!signedIn) return;
    ensurePill();
    var st = s.status, text = LABEL[st] || "Online";
    if (st === "syncing" && s.progress && s.progress.total) text += " " + s.progress.done + "/" + s.progress.total;
    if (s.pending && st !== "syncing") text += " · " + s.pending + " pending";
    if (s.conflicts) text += " · " + s.conflicts + " need review";
    pill.textContent = text; pill.setAttribute("data-state", st);
    pill.title = s.error || ("Last sync: " + (s.lastSync ? new Date(s.lastSync).toLocaleString() : "never"));
    document.documentElement.setAttribute("data-sh-connection", s.online ? "online" : "offline");
    var sc = document.querySelector("[data-sync-center]"); if (sc) renderCenter(s);
  }
  core.on("status", render);

  /* ---------- connectivity + automatic sync ---------- */
  var wasOffline = false;
  function connectionTick() {
    return core.checkConnection().then(function (up) {
      if (up && (wasOffline || core.state().pending)) { wasOffline = false; return core.syncNow(); }
      if (!up) wasOffline = true;
    });
  }
  window.addEventListener("online", connectionTick);
  window.addEventListener("offline", function () { wasOffline = true; core.checkConnection(); });
  setInterval(connectionTick, 20000);

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
    if (navigator.onLine !== false && core.state().online) return;                      // online: normal submit
    var action; try { action = new URL(form.getAttribute("action") || location.pathname, location.href); } catch (e) { return; }
    if (action.origin !== location.origin || !core.canQueuePath(action.pathname)) return; // login, billing, etc. need the server
    ev.preventDefault(); ev.stopImmediatePropagation();
    var fd = new FormData(form), fields = [], files = [], jobs = [];
    fd.forEach(function (v, k) {
      if (v instanceof File) { if (v.size) jobs.push(v.arrayBuffer().then(function (buf) { files.push({ field: k, name: v.name, type: v.type, buffer: buf }); })); }
      else fields.push([k, v]);
    });
    Promise.all(jobs).then(function () {
      return core.enqueue({ method: "POST", url: action.pathname + action.search, kind: "form", body: fields, files: files, label: (document.title || "Form") });
    }).then(function () {
      toast("Saved on this device. It will be sent automatically when the connection returns.");
      var btn = form.querySelector('[type="submit"]'); if (btn) { btn.disabled = false; }
    }).catch(function (err) { toast(err && err.message ? err.message : "This could not be saved offline."); });
  }, true);

  /* ---------- logout: never throw away queued work silently; always forget cached pages ---------- */
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href$="/logout"]');
    if (!a || !signedIn) return;
    var s = core.state(), n = s.pending + s.failed + s.conflicts;
    if (n && !window.confirm("You have " + n + " change(s) that have not reached the server. They stay safely on this device and will sync the next time you sign in with a connection. Sign out now?")) { ev.preventDefault(); return; }
    swSend({ type: "PURGE_PAGES" });
  }, true);

  /* ---------- Sync Center: "this device" panel ---------- */
  function renderCenter(s) {
    var root = document.querySelector("[data-sync-center]"); if (!root) return;
    function set(k, v) { var el = root.querySelector('[data-k="' + k + '"]'); if (el) el.textContent = v; }
    set("status", LABEL[s.status] || s.status); set("connection", s.online ? "Connected to the school server" : "No connection to the school server");
    set("pending", s.pending); set("failed", s.failed); set("conflicts", s.conflicts); set("synced", s.synced);
    set("last", s.lastSync ? new Date(s.lastSync).toLocaleString() : "Never"); set("error", s.error || "None");
    set("enc", s.encrypted ? "Queued changes are encrypted on this device" : "This browser cannot encrypt local data (use HTTPS or localhost)");
    var bar = root.querySelector("[data-k=bar]"); if (bar) { var p = s.progress && s.progress.total ? Math.round(100 * s.progress.done / s.progress.total) : (s.status === "completed" ? 100 : 0); bar.style.width = p + "%"; bar.setAttribute("aria-valuenow", p); }
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
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-sync-now]");
    if (b) { ev.preventDefault(); core.syncNow({ manual: true }); }
  });
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-resolve]");
    if (!b) return;
    ev.preventDefault();
    var id = b.getAttribute("data-conflict"), choice = b.getAttribute("data-resolve");
    if (choice === "apply_offline" && !confirm("Apply the offline version? It replaces the value currently on the server and is recorded in the audit trail.")) return;
    core.sessionInfo().then(function (info) {
      return fetch("/api/sync/conflicts/" + id + "/resolve", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": info.csrf }, body: JSON.stringify({ resolution: choice }) });
    }).then(function (r) { return r.json(); }).then(function (j) { if (j.ok) location.reload(); else alert(j.error || "Could not resolve."); });
  });

  /* ---------- start ---------- */
  core.ready.then(function () {
    render(core.state());
    if (!signedIn) return;
    swSend({ type: "SET_USER", fingerprint: fingerprint });
    core.checkConnection().then(function (up) {
      if (!up) { wasOffline = true; gate(); return; }
      core.sessionInfo().then(function () {
        core.seedScoreVersions();
        if (core.state().pending) core.syncNow();
        /* fetch the main screens once so they open offline */
        var urls = {}; urls[location.pathname + location.search] = 1;
        document.querySelectorAll("a.nav-item[href], .mobile-tabs a[href]").forEach(function (a) { try { var u = new URL(a.href); if (u.origin === location.origin && !/logout|^\/platform|^\/api\//.test(u.pathname)) urls[u.pathname + u.search] = 1; } catch (e) {} });
        var key = "sh-warm-" + fingerprint, last = 0;
        try { last = parseInt(localStorage.getItem(key), 10) || 0; } catch (e) {}
        if (Date.now() - last > 3600000) {                                   // once an hour per user, not on every page load
          try { localStorage.setItem(key, String(Date.now())); } catch (e) {}
          setTimeout(function () { swSend({ type: "WARM", urls: Object.keys(urls) }); }, 3000);
        }
      }).catch(function () {});
    });
  });
})();
