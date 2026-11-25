/* Offline sign-in page (shown by the service worker when nobody is signed in and the school server cannot be reached).
   The password is checked on this device against the key wrapped when the person first signed in online. */
(function () {
  "use strict";
  var core = SHOffline.boot(), $ = function (id) { return document.getElementById(id); };
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
  function show(which) { ["signin", "signedin", "online"].forEach(function (n) { $(n).hidden = n !== which; }); $("title").textContent = which === "online" ? "Connected" : "You're offline"; }
  core.ready.then(function () { return core.checkConnection(); }).then(function (up) {
    if (up) return show("online");
    return core.metaGet("fingerprint").then(function (fp) {
      return core.crypto.isUnlocked(fp).then(function (open) { show(open ? "signedin" : "signin"); });
    });
  });
  $("switch").addEventListener("click", function () {
    core.metaGet("fingerprint").then(function (fp) { return core.crypto.lock(fp); }).then(function () { return swPost({ type: "LOCK" }); }).then(function () { show("signin"); });
  });
  $("offForm").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var f = ev.target, btn = f.querySelector("button"); btn.disabled = true; $("msg").textContent = "";
    core.offlineLogin(f.elements.username.value, f.elements.school_code.value, f.elements.password.value).then(function (r) {
      if (!r.ok) { $("msg").textContent = r.error; btn.disabled = false; return; }
      return swPost({ type: "SET_USER", fingerprint: r.fingerprint }).then(function () { location.href = "/dashboard"; });
    });
  });
})();
