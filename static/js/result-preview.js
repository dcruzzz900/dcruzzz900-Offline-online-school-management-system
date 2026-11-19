/* V106: React live preview for Result Display Settings.
   The settings form stays a normal server-rendered <form> (it still saves with a plain POST, so nothing depends on JavaScript to
   save). This component owns the PREVIEW:
     - it reads every control of the form into React state on each input/change (colours, logo, watermark, paper size, orientation,
       every show/hide switch, designs ...), so the preview reacts the instant a setting changes;
     - presentational settings (accent / secondary colour, paper size, orientation) are applied to the preview immediately in the
       browser; settings that change what the sheet SHOWS are re-rendered by the server through the real result sheet template
       (POST /api/result-display-settings/preview, debounced, older requests cancelled), so the preview always matches print/PDF;
     - it keeps the ON/OFF captions, an "unsaved changes" counter and a Reset button in step with the form. */
(function () {
  "use strict";
  var UI = window.SchoolHubUI; if (!UI) return;
  var React = UI.React, h = UI.h, useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useCallback = React.useCallback;
  var root = document.getElementById("rdsLive"), form = root && document.getElementById(root.getAttribute("data-form"));
  if (!root || !form) return;

  var URL_ = root.getAttribute("data-url"), CSRF = root.getAttribute("data-csrf");
  var PAPER = {}; try { PAPER = JSON.parse(root.getAttribute("data-paper") || "{}"); } catch (e) {}
  var initialHtml = (document.getElementById("rdsPrevInner") || {}).innerHTML || "";

  function readForm() {
    var v = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name === "csrf_token" || el.disabled) return;
      if (el.type === "checkbox") { v[el.name] = el.checked ? "1" : "0"; }
      else if (el.type === "radio") { if (el.checked) v[el.name] = el.value; }
      else if (el.type === "file" || el.type === "submit" || el.type === "button") { /* not previewable */ }
      else v[el.name] = el.value;
    });
    return v;
  }
  function countChanged(a, b) { var n = 0; Object.keys(b).forEach(function (k) { if (String(a[k]) !== String(b[k])) n++; }); return n; }
  function pageSize(values) {
    var dims = PAPER[values.paper_size] || PAPER.A4 || [210, 297], w = dims[0], hh = dims[1];
    var land = values.page_orientation === "landscape";
    return land ? [Math.max(w, hh), Math.min(w, hh)] : [Math.min(w, hh), Math.max(w, hh)];
  }

  function Preview() {
    var s0 = useState(function () { return readForm(); }), values = s0[0], setValues = s0[1];
    var baseline = useRef(values.current || values);
    var s1 = useState(initialHtml), html = s1[0], setHtml = s1[1];
    var s2 = useState("idle"), status = s2[0], setStatus = s2[1];   // idle | loading | error
    var s3 = useState(""), error = s3[0], setError = s3[1];
    var s4 = useState([]), invalid = s4[0], setInvalid = s4[1];
    var frame = useRef(null), inner = useRef(null);
    var debounced = UI.useDebounced(values, 140);

    // 1) form -> React state, on every input / change (and after a form reset)
    useEffect(function () {
      var sync = function () { setValues(readForm()); };
      form.addEventListener("input", sync); form.addEventListener("change", sync);
      form.addEventListener("reset", function () { setTimeout(sync, 0); });
      return function () { form.removeEventListener("input", sync); form.removeEventListener("change", sync); };
    }, []);

    // 2) ON / OFF captions follow the switches immediately
    useEffect(function () {
      document.querySelectorAll("[data-rds-state]").forEach(function (n) {
        var k = n.getAttribute("data-rds-state"); if (k in values) n.textContent = values[k] === "1" ? "ON" : "OFF";
      });
    }, [values]);

    // 3) server render of the real sheet for the CURRENT values (debounced, cancellable)
    useEffect(function () {
      var ctl = new AbortController(); setStatus("loading");
      UI.api(URL_, { body: { values: debounced }, csrf: CSRF, signal: ctl.signal }).then(function (p) {
        setHtml(p.html); setInvalid(p.invalid || []); setStatus("idle"); setError("");
      }).catch(function (e) { if (e.name === "AbortError") return; setStatus("error"); setError(e.message || "Preview unavailable."); });
      return function () { ctl.abort(); };
    }, [debounced]);

    // 4) instant, in-browser application of presentational settings (before the server answer arrives)
    var wh = pageSize(values), ratio = wh[1] / wh[0];
    useEffect(function () {
      var sheet = inner.current && inner.current.querySelector(".rs-sheet"); if (!sheet) return;
      var a = /^#[0-9a-fA-F]{6}$/, acc = a.test(values.accent_color || "") ? values.accent_color : null, sec = a.test(values.secondary_color || "") ? values.secondary_color : null;
      if (acc) sheet.style.setProperty("--rs-accent", acc);
      if (sec) sheet.style.setProperty("--rs-second", sec);
    }, [values.accent_color, values.secondary_color, html]);

    // 5) scale the sheet to the column width (the old result-fit.js job), re-run when content or width changes
    var dimsRef = useRef(wh); dimsRef.current = wh;
    var fit = useCallback(function () {
      var box = frame.current, wrap = inner.current; if (!box || !wrap) return;
      var sheet = wrap.querySelector(".rs-sheet"); if (!sheet) return;
      // lay the sheet out at its REAL paper width (so every column is present, exactly like print), then scale it to the column
      var px = dimsRef.current[0] * 96 / 25.4;
      sheet.style.zoom = ""; sheet.style.width = px + "px"; sheet.style.maxWidth = "none";
      var z = Math.min(1, (box.clientWidth - 2) / px); sheet.style.zoom = z;
    }, []);
    useEffect(function () { fit(); }, [html, values.paper_size, values.page_orientation, fit]);
    useEffect(function () {
      var ro = window.ResizeObserver ? new ResizeObserver(fit) : null; if (ro && frame.current) ro.observe(frame.current);
      window.addEventListener("resize", fit); return function () { if (ro) ro.disconnect(); window.removeEventListener("resize", fit); };
    }, [fit]);

    var changed = countChanged(baseline.current, values);
    var label = (PAPER[values.paper_size] ? values.paper_size : "Custom") + " · " + (values.page_orientation === "landscape" ? "Landscape" : "Portrait") + " · " + Math.round(wh[0]) + "×" + Math.round(wh[1]) + " mm";

    return h("div", { className: "rds-live" },
      h("div", { className: "d-flex flex-wrap align-items-center gap-2 mb-2" },
        h("h3", { className: "m-0 me-auto" }, "Live preview ", h("small", { className: "muted" }, "(sample data)")),
        status === "loading" && h("span", { className: "spinner-border spinner-border-sm text-secondary", role: "status", "aria-label": "Updating preview" }),
        h("span", { className: "badge " + (changed ? "text-bg-warning" : "bg-body-secondary text-body border"), "aria-live": "polite" }, changed ? changed + " unsaved change" + (changed === 1 ? "" : "s") : "No changes"),
        h("button", { type: "button", className: "btn btn-secondary btn-sm", disabled: !changed, onClick: function () { form.reset(); } }, "Reset")),
      h("div", { className: "small muted mb-2" }, label),
      error && h("div", { className: "alert alert-warning py-2 small", role: "alert" }, "Preview not updated: " + error),
      invalid.length > 0 && h("div", { className: "alert alert-info py-2 small" }, "Not previewed yet (invalid value): " + invalid.join(", ")),
      h("div", { className: "rds-prev rds-page-frame", ref: frame, style: { opacity: status === "loading" ? 0.7 : 1, transition: "opacity .12s" } },
        h("div", { id: "rdsPrevInner", ref: inner, dangerouslySetInnerHTML: { __html: html } })));
  }

  var mountPoint = document.getElementById("rdsPrev"); if (!mountPoint) return;
  var host = document.createElement("div"); root.replaceChild(host, root.querySelector("h3")); mountPoint.remove(); root.appendChild(host);
  UI.mount(host, h(Preview));
})();
