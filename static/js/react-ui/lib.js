/* V106: tiny shared helpers for the React components (no build step: React.createElement, loaded from the pinned CDN build).
   window.SchoolHubUI = { h, useDebounced, api, mount } */
(function () {
  "use strict";
  if (!window.React || !window.ReactDOM) { window.SchoolHubUI = null; return; }
  var React = window.React;
  var h = React.createElement;

  function useDebounced(value, ms) {
    var st = React.useState(value), v = st[0], setV = st[1];
    React.useEffect(function () { var t = setTimeout(function () { setV(value); }, ms); return function () { clearTimeout(t); }; }, [value, ms]);
    return v;
  }

  /* JSON fetch with the CSRF header the /api/ routes require. Rejects with an Error carrying .status and .payload. */
  function api(url, o) {
    o = o || {};
    var headers = { "Accept": "application/json" };
    if (o.body !== undefined) headers["Content-Type"] = "application/json";
    if (o.csrf) headers["X-CSRF-Token"] = o.csrf;
    return fetch(url, { method: o.method || (o.body !== undefined ? "POST" : "GET"), headers: headers, credentials: "same-origin",
      body: o.body !== undefined ? JSON.stringify(o.body) : undefined, signal: o.signal }).then(function (r) {
      if (r.redirected && /\/login/.test(r.url)) { var e0 = new Error("Your session has expired - please sign in again."); e0.status = 401; throw e0; }
      return r.json().catch(function () { return {}; }).then(function (payload) {
        if (!r.ok || payload.ok === false) { var e = new Error(payload.error || ("Request failed (" + r.status + ")")); e.status = r.status; e.payload = payload; throw e; }
        return payload;
      });
    });
  }

  function mount(el, node) {
    var root = ReactDOM.createRoot(el);
    root.render(node);
    return root;
  }

  window.SchoolHubUI = { React: React, h: h, useDebounced: useDebounced, api: api, mount: mount };
})();
