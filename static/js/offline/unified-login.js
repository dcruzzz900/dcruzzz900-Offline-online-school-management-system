/* My School Hub - ONE login page for online and offline use (V116).
   - The page detects the connection by itself (browser events + a small ping to the school server) and says which mode it is in.
   - ONLINE: the normal form goes to the Flask backend (/login). Roles, permissions, rate limits and school rules are all the server's.
   - OFFLINE: only people who have already signed in on THIS device while online can sign in. Their password is checked on the device by
     trying to open the encrypted key that was wrapped with it at that first online sign-in (see offline-core.js). The password itself
     is never stored. A device that has never been used online has nobody enrolled, so offline sign-in is refused there.
   - The cached copy of this page is anonymous (no session, no school data); when it was opened offline its CSRF token is stale, so a
     fresh one is fetched before the form goes to the server. */
(function () {
  "use strict";
  var form = document.getElementById("unifiedLoginForm"), badge = document.getElementById("loginConn");
  if (!form || !window.SHOffline) return;
  var core = SHOffline.boot();
  var up = null, enrolled = 0, loadedOffline = false, busy = false;
  var MSG = {
    checking: "Checking your connection…",
    online: "Online — you will sign in through the school server.",
    offline_ok: "Offline — you can sign in with this device if you have signed in here before while online.",
    offline_new: "Offline — this device has not been set up yet. Connect to the internet and sign in once; after that you can sign in offline here.",
    offline_https: "Offline — offline sign-in needs a secure (HTTPS) connection on this device. Connect to the internet to sign in."
  };
  var FIRST_TIME = "This device has not been set up for offline sign-in. Connect to the internet and sign in once first.";
  var NEXT_BLOCK = /^\/(login|logout|offline|api\/|static\/|platform|student\/|parent\/|service-worker|manifest)/;

  function $(sel) { return form.querySelector(sel); }
  function setMsg(text, kind) {
    var el = document.getElementById("loginOfflineMsg");
    if (!el) { el = document.createElement("div"); el.id = "loginOfflineMsg"; el.className = "login-offline-msg"; el.setAttribute("role", "alert"); form.insertBefore(el, form.querySelector("button[type=submit]")); }
    el.textContent = text || ""; el.hidden = !text; el.dataset.kind = kind || "error";
  }
  function render() {
    var state = up === null ? "checking" : up ? "online" : !core.crypto.enabled ? "offline_https" : enrolled ? "offline_ok" : "offline_new";
    if (badge) { badge.textContent = MSG[state]; badge.dataset.state = state; }
    form.dataset.mode = up === null ? "checking" : up ? "online" : "offline";
    return state;
  }
  function countEnrolled() {
    if (!core.crypto.listUsers) return Promise.resolve(0);
    return core.crypto.listUsers().then(function (u) { return u.length; }).catch(function () { return 0; });
  }
  function refresh() {
    return core.ready.then(function () { return core.checkConnection(); }).then(function (isUp) {
      var wasUp = up; up = isUp;
      if (wasUp === false && isUp && loadedOffline) { loadedOffline = false; return freshToken().then(function () { return isUp; }); }
      return isUp;
    }).then(function (isUp) { return countEnrolled().then(function (n) { enrolled = n; render(); return isUp; }); });
  }
  /* the anonymous cached page carries a throw-away token; ask the server for the real one (keeps whatever was typed) */
  function freshToken() {
    return fetch("/login", { cache: "no-store", credentials: "same-origin" }).then(function (r) { return r.text(); }).then(function (t) {
      var m = /name="csrf_token" value="([^"]+)"/.exec(t), f = form.elements.csrf_token; if (m && f) f.value = m[1];
    }).catch(function () {});
  }
  /* post to the service worker and WAIT until it has handled the message (navigating earlier would race with it) */
  function swPost(msg) {
    if (!("serviceWorker" in navigator)) return Promise.resolve();
    return navigator.serviceWorker.ready.then(function (reg) {
      return new Promise(function (resolve) {
        var ch = new MessageChannel(); ch.port1.onmessage = function () { resolve(); }; setTimeout(resolve, 3000);
        (reg.active || navigator.serviceWorker.controller).postMessage(msg, [ch.port2]);
      });
    }).catch(function () {});
  }
  function landing() {
    var p = location.pathname + location.search;
    return p.charAt(0) === "/" && p.charAt(1) !== "/" && !NEXT_BLOCK.test(p) && p !== "/" ? p : "/dashboard";
  }
  function forget() { try { sessionStorage.removeItem("sh-login"); } catch (e) {} }   // offline-ui stashes the typed password for the NEXT online page: never keep it for an offline attempt

  function signInOffline() {
    var user = form.elements.username.value, pass = form.elements.password.value, school = form.elements.school_code ? form.elements.school_code.value : "";
    forget();
    if (form.elements.class_code && form.elements.class_code.value.trim()) return Promise.resolve({ ok: false, error: "A first-time student sign-in with a Class Login Code needs an internet connection." });
    if (!core.crypto.enabled) return Promise.resolve({ ok: false, error: MSG.offline_https });
    return countEnrolled().then(function (n) {
      enrolled = n; render();
      if (!n) return { ok: false, error: FIRST_TIME };            // unregistered device: refuse, do not even try the password
      return core.offlineLogin(user, school, pass);
    }).then(function (r) {
      if (!r.ok) return r;
      return swPost({ type: "SET_USER", fingerprint: r.fingerprint }).then(function () { return r; });
    });
  }

  form.addEventListener("submit", function (ev) {
    if (busy) return;
    ev.preventDefault();
    busy = true;
    var btn = form.querySelector("button[type=submit]"); if (btn) btn.disabled = true; setMsg("");
    var done = function () { busy = false; if (btn) btn.disabled = false; };
    /* one retry before concluding "offline", so a slow school server is not mistaken for no connection */
    refresh().then(function (isUp) { return isUp ? true : new Promise(function (r) { setTimeout(r, 900); }).then(refresh); }).then(function (isUp) {
      if (isUp) {
        var go = function () { busy = false; HTMLFormElement.prototype.submit.call(form); };
        return loadedOffline ? freshToken().then(go) : go();
      }
      return signInOffline().then(function (r) {
        forget();
        if (!r.ok) { setMsg(r.error); form.elements.password.value = ""; form.elements.password.focus(); return done(); }
        form.elements.password.value = ""; location.href = landing();
      });
    }).catch(function () { setMsg("Something went wrong. Check your connection and try again."); done(); });
  });

  window.addEventListener("online", refresh);
  window.addEventListener("offline", function () { up = false; refresh(); });
  setInterval(function () { if (!document.hidden && !busy) refresh(); }, 8000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  render();
  /* was this page opened without the server? (then its token is stale until the connection returns) */
  refresh().then(function (isUp) { if (!isUp) loadedOffline = true; else freshToken(); });
})();
