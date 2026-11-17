/* V107: Theme & Branding - live background preview (React). A faithful port of branding_backgrounds.py (same presets, same mixing, same
   contrast-guaranteeing scrim); tests/v107 runs both on thousands of random inputs and requires identical output, so the preview is exactly
   what the server will save. Reads the settings form, renders a mini dashboard and a mini sign-in screen in light or dark, instantly. */
(function () {
  "use strict";
  var HEX = /^#[0-9a-fA-F]{6}$/, MODES = ["default", "preset", "solid", "gradient"], DARK_BASE = "#0B1120";
  var PRESETS = {};   // filled from the page: { key: [label, la, lb, da, db, angle] }

  function rgb(h) { h = h.replace("#", ""); return [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)]; }
  function lum(h) { var c = rgb(h).map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
  function contrast(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  function pyround(x) { var f = Math.floor(x), d = x - f; if (d < 0.5) return f; if (d > 0.5) return f + 1; return f % 2 === 0 ? f : f + 1; }   // Python's banker's rounding
  function hex2(n) { n = Math.max(0, Math.min(255, n)); return (n < 16 ? "0" : "") + n.toString(16); }
  function mix(c, base, pct) { var a = rgb(c), b = rgb(base), k = pct / 100; return "#" + [0, 1, 2].map(function (i) { return hex2(pyround(a[i] * (1 - k) + b[i] * k)); }).join(""); }
  function readableInk() {
    var bgs = Array.prototype.slice.call(arguments), best = "#ffffff", score = -1;
    ["#ffffff", "#111827"].forEach(function (ink) { var w = Math.min.apply(null, bgs.map(function (b) { return contrast(ink, b); })); if (w > score) { best = ink; score = w; } });
    return best;
  }
  function scrim(ink, cols) {
    var base = ink === "#ffffff" ? "#000000" : "#ffffff";
    for (var step = 0; step < 46; step++) { var a = step * 0.02; if (Math.min.apply(null, cols.map(function (c) { return contrast(ink, mix(c, base, a * 100)); })) >= 4.6) return Math.round(a * 100) / 100; }
    return 0.9;
  }
  function clean(mode, preset, c1, c2, angle) {
    mode = MODES.indexOf(mode) > -1 ? mode : "default"; preset = PRESETS[preset] ? preset : "sky";
    c1 = typeof c1 === "string" && HEX.test(c1) ? c1.toLowerCase() : "#e6f0ff"; c2 = typeof c2 === "string" && HEX.test(c2) ? c2.toLowerCase() : "#ffffff";
    var n = parseInt(angle, 10); angle = isNaN(n) ? 160 : Math.max(0, Math.min(360, n));
    return [mode, preset, c1, c2, angle];
  }
  function build(mode, preset, c1, c2, angle) {
    var v = clean(mode, preset, c1, c2, angle); mode = v[0]; preset = v[1]; c1 = v[2]; c2 = v[3]; angle = v[4];
    if (mode === "default") return null;
    var la, lb, da, db, ang;
    if (mode === "preset") { var p = PRESETS[preset]; la = p[1]; lb = p[2]; da = p[3]; db = p[4]; ang = p[5]; }
    else if (mode === "solid") { la = lb = c1; da = db = mix(c1, DARK_BASE, 78); ang = 180; }
    else { la = c1; lb = c2; ang = angle; da = mix(c1, DARK_BASE, 78); db = mix(c2, DARK_BASE, 78); }
    function one(a, b) {
      var grad = a === b ? a : "linear-gradient(" + ang + "deg," + a + "," + b + ")", ink = readableInk(a, b), alpha = scrim(ink, [a, b]);
      if (alpha) { var s = ink === "#ffffff" ? "0,0,0" : "255,255,255"; grad = "linear-gradient(rgba(" + s + "," + alpha + "),rgba(" + s + "," + alpha + "))," + grad; }
      return [grad, ink];
    }
    var L = one(la, lb), D = one(da, db);
    return { light: L[0], dark: D[0], ink_light: L[1], ink_dark: D[1] };
  }
  window.SchoolHubBg = { build: build, setPresets: function (p) { PRESETS = p; } };

  var root = document.getElementById("bgPreview"); if (!root) return;
  var form = document.getElementById("themeForm"); if (!form) return;
  try { var raw = JSON.parse(root.getAttribute("data-presets")), P = {}; Object.keys(raw).forEach(function (k) { P[k] = [raw[k].label, raw[k].la, raw[k].lb, raw[k].da, raw[k].db, raw[k].angle]; }); PRESETS = P; } catch (e) { return; }
  var CDN = ["https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js", "https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"];
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.crossOrigin = "anonymous"; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  (window.React && window.ReactDOM ? Promise.resolve() : load(CDN[0]).then(function () { return load(CDN[1]); })).then(function () {
    var React = window.React, h = React.createElement;
    function read() {
      var v = {}; Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name) return; if (el.type === "checkbox") v[el.name] = el.checked ? "1" : "0"; else if (el.type === "radio") { if (el.checked) v[el.name] = el.value; } else v[el.name] = el.value;
      }); return v;
    }
    function Mini(p) {
      var bg = p.bg ? (p.dark ? p.bg.dark : p.bg.light) : null, ink = p.bg ? (p.dark ? p.bg.ink_dark : p.bg.ink_light) : (p.dark ? "#F1F5F9" : "#172033");
      var surface = p.dark ? "#182235" : "#ffffff", text = p.dark ? "#F1F5F9" : "#172033", std = p.dark ? "#0B1120" : "#f5f8fc";
      if (p.kind === "auth") {
        var abg = p.apply && bg ? bg : (p.dark ? "linear-gradient(180deg,#0f1c33,#0B1120)" : "linear-gradient(180deg,#f4f8ff,#f8fafc)");
        return h("div", { className: "bgm bgm-auth", style: { background: abg } },
          h("div", { className: "bgm-card", style: { background: surface, color: text } }, h("div", { className: "bgm-hero", style: { background: p.primary } }, "Welcome Back"), h("div", { className: "bgm-line" }), h("div", { className: "bgm-line short" }), h("div", { className: "bgm-btn", style: { background: p.primary } }, "Sign in")),
          h("div", { className: "bgm-cap", style: { color: p.apply && bg ? ink : text } }, p.apply ? "Custom background ON" : "Standard background"));
      }
      return h("div", { className: "bgm bgm-dash", style: { background: bg || std } },
        h("div", { className: "bgm-top", style: { background: surface, color: text } }, "My School"),
        h("div", { className: "bgm-head", style: { color: ink } }, h("b", null, "Welcome, Administrator!"), h("span", null, "Here is an overview of your school system.")),
        h("div", { className: "bgm-cards" }, [1, 2, 3].map(function (i) { return h("div", { key: i, className: "bgm-c", style: { background: surface, color: text } }, h("b", null, i * 12), h("span", null, "Students")); })));
    }
    function App() {
      var s0 = React.useState(read()), v = s0[0], setV = s0[1];
      var s1 = React.useState(document.documentElement.getAttribute("data-bs-theme") === "dark"), dark = s1[0], setDark = s1[1];
      React.useEffect(function () {
        var f = function () { setV(read()); }; form.addEventListener("input", f); form.addEventListener("change", f);
        var t = function () { setDark(document.documentElement.getAttribute("data-bs-theme") === "dark"); }; window.addEventListener("sh-theme-change", t);
        return function () { form.removeEventListener("input", f); form.removeEventListener("change", f); window.removeEventListener("sh-theme-change", t); };
      }, []);
      var bg = build(v.bg_mode, v.bg_preset, v.bg_color1, v.bg_color2, v.bg_angle), apply = v.bg_apply_auth === "1", primary = v.dashboard_primary_color || "#1f6feb";
      return h("div", null,
        h("div", { className: "d-flex align-items-center gap-2 mb-2" }, h("b", { className: "me-auto" }, "Live preview"),
          h("div", { className: "btn-group btn-group-sm", role: "group", "aria-label": "Preview theme" },
            h("button", { type: "button", className: "btn " + (dark ? "btn-secondary" : "btn-primary"), "aria-pressed": !dark, onClick: function () { setDark(false); } }, "Light"),
            h("button", { type: "button", className: "btn " + (dark ? "btn-primary" : "btn-secondary"), "aria-pressed": dark, onClick: function () { setDark(true); } }, "Dark"))),
        h("div", { className: "row g-3" }, h("div", { className: "col-md-7" }, h("div", { className: "small muted mb-1" }, "Dashboard"), h(Mini, { kind: "dash", bg: bg, dark: dark, primary: primary })),
          h("div", { className: "col-md-5" }, h("div", { className: "small muted mb-1" }, "Sign-in page"), h(Mini, { kind: "auth", bg: bg, dark: dark, apply: apply, primary: primary }))));
    }
    ReactDOM.createRoot(root).render(h(App));
  }).catch(function () {});
})();
