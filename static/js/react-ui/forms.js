/* V110: shared React form layer for EVERY data-entry form (students, staff, parents, admissions, attendance, scores, subjects,
   timetable, profiles, branding, school settings, materials, promotion, approvals ...).

   How it works (no build step, React.createElement, same pinned CDN build as the other react-ui files):
   * Every server-rendered POST form inside the signed-in app is upgraded automatically. The form keeps its own action URL, its
     CSRF token and its field names, so it still posts to the SAME Flask route: authentication, role permissions, tenant isolation,
     business rules and database validation all run on the server exactly as before. Nothing here can bypass them.
   * Frontend validation: required / pattern / min / max / length / e-mail / number / date / data-match, with plain-language messages
     next to the field and a summary above the form. The server still validates everything again.
   * One submission at a time: the buttons lock, show "Saving...", and a second click / Enter press is ignored until the server answers.
   * Clear feedback: loading, success and error messages (server flash messages are read and shown; typed input is kept on errors).
   * Opt out of a form with the attribute data-no-hub (forms with their own inline onsubmit, a target, or GET forms are skipped).
   * Reusable pieces for new React forms are exported on window.SchoolHubForms (Field, SelectField, FormStatus, SubmitButton, useSubmit). */
(function () {
  "use strict";
  if (typeof window === "undefined") return;

  /* ------------------------------------------------------------------ pure helpers (unit-tested in node) */
  function cleanText(s) { return String(s == null ? "" : s).replace(/\s+/g, " ").replace(/\*/g, "").trim(); }

  function labelOf(el) {
    var t = "";
    if (el.id) { var l = el.ownerDocument.querySelector('label[for="' + String(el.id).replace(/"/g, '\\"') + '"]'); if (l) t = l.textContent; }
    if (!t) { var p = el.closest ? el.closest("label") : null; if (p) { var c = p.cloneNode(true); [].forEach.call(c.querySelectorAll("input,select,textarea,small,.muted"), function (n) { n.remove(); }); t = c.textContent; } }
    if (!t) t = el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "This field";
    t = cleanText(t);
    return t.length > 60 ? t.slice(0, 57) + "…" : (t || "This field");
  }

  /* One message for one control, or "" when it is fine. `v` is the control's current value (already read by the caller). */
  function messageFor(label, o) {
    var v = o.value == null ? "" : String(o.value), type = (o.type || "text").toLowerCase();
    if (o.required && (type === "checkbox" ? !o.checked : v.trim() === "")) return label + (type === "checkbox" ? " must be ticked." : " is required.");
    if (v === "") return "";
    if (type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())) return label + ": enter a valid e-mail address.";
    if (type === "url" && !/^https?:\/\/\S+$/i.test(v.trim())) return label + ": enter a valid web address starting with http:// or https://.";
    if (type === "number") {
      var n = Number(v); if (!isFinite(n)) return label + " must be a number.";
      if (o.min !== "" && o.min != null && n < Number(o.min)) return label + " cannot be less than " + o.min + ".";
      if (o.max !== "" && o.max != null && n > Number(o.max)) return label + " cannot be more than " + o.max + ".";
    }
    if (type === "date" || type === "datetime-local" || type === "month" || type === "time") {
      if (o.min && v < o.min) return label + " cannot be earlier than " + o.min + ".";
      if (o.max && v > o.max) return label + " cannot be later than " + o.max + ".";
    }
    if (o.minlength > 0 && v.length < o.minlength) return label + " must be at least " + o.minlength + " characters.";
    if (o.maxlength > 0 && v.length > o.maxlength) return label + " must be at most " + o.maxlength + " characters.";
    if (o.pattern) { try { if (!new RegExp("^(?:" + o.pattern + ")$").test(v)) return o.title ? label + ": " + o.title : label + " is not in the expected format."; } catch (e) { /* bad pattern: let the server decide */ } }
    if (o.matchValue != null && v !== o.matchValue) return label + " does not match.";
    return "";
  }

  /* Reads every server flash message out of a returned page: [{cat, text}] */
  function readFlashes(doc) {
    var out = [];
    [].forEach.call(doc.querySelectorAll(".flash"), function (n) {
      var cat = "info", m = /(?:^|\s)flash-(\w+)/.exec(n.className || ""); if (m) cat = m[1];
      var c = n.cloneNode(true); [].forEach.call(c.querySelectorAll("button"), function (b) { b.remove(); });
      var text = cleanText(c.textContent); if (text) out.push({ cat: cat, text: text });
    });
    return out;
  }
  function isErrorCat(c) { return c === "error" || c === "danger"; }

  function statusMessage(status) {
    if (status === 400) return "The request was refused (your page may be out of date). Reload the page and try again.";
    if (status === 401) return "Your session has expired. Please sign in again.";
    if (status === 403) return "You do not have permission to do this.";
    if (status === 404) return "That record or page no longer exists.";
    if (status === 413) return "The file or form is too large to upload.";
    if (status === 429) return "Too many attempts. Please wait a moment and try again.";
    if (status >= 500) return "The server had a problem and nothing was confirmed saved. Please try again in a moment.";
    return "The request could not be completed (error " + status + ").";
  }

  var H = { cleanText: cleanText, messageFor: messageFor, readFlashes: readFlashes, statusMessage: statusMessage, isErrorCat: isErrorCat, labelOf: labelOf };
  window.SchoolHubForms = Object.assign(window.SchoolHubForms || {}, { _internals: H });
  if (typeof document === "undefined" || !document.querySelectorAll) return;

  /* ------------------------------------------------------------------ boot */
  var CDN = ["https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js", "https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"];
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.crossOrigin = "anonymous"; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  function ensureReact() { if (window.React && window.ReactDOM) return Promise.resolve(); return load(CDN[0]).then(function () { return load(CDN[1]); }); }

  var SKIP_ACTION = /\/(logout|login|student-login|platform-login)(\/|$|\?)/;
  function eligible(form) {
    if (form.hasAttribute("data-no-hub") || form.closest("[data-no-hub]")) return false;
    if ((form.getAttribute("method") || "get").toLowerCase() !== "post") return false;
    if (form.hasAttribute("onsubmit")) return false;
    var t = form.getAttribute("target"); if (t && t !== "_self") return false;
    if (SKIP_ACTION.test(form.getAttribute("action") || "")) return false;
    return true;
  }
  var found = [].filter.call(document.querySelectorAll("form"), eligible);
  var hasStoredToast = false;
  try { hasStoredToast = !!sessionStorage.getItem("hubToast"); } catch (e) { /* storage blocked */ }
  if (!found.length && !hasStoredToast) return;

  ensureReact().then(function () {
    var React = window.React, h = React.createElement;

    /* ---------------------------------------------------------------- reusable components */
    function FormStatus(p) {                     // kind: loading | success | error | invalid | warning
      if (!p || !p.kind) return null;
      var cls = { loading: "alert-info", success: "alert-success", error: "alert-danger", invalid: "alert-warning", warning: "alert-warning" }[p.kind] || "alert-info";
      var assertive = p.kind === "error" || p.kind === "invalid";
      return h("div", { className: "hub-status alert " + cls, role: assertive ? "alert" : "status", "aria-live": assertive ? "assertive" : "polite" },
        p.kind === "loading" ? h("span", { className: "hub-spin", "aria-hidden": "true" }) : null,
        h("div", { className: "hub-status-body" },
          p.title ? h("strong", null, p.title) : null,
          p.message ? h("div", null, p.message) : null,
          p.items && p.items.length ? h("ul", { className: "hub-status-list" }, p.items.map(function (t, i) { return h("li", { key: i }, t); })) : null),
        p.onClose && p.kind !== "loading" ? h("button", { type: "button", className: "btn-close hub-status-x", "aria-label": "Dismiss", onClick: p.onClose }) : null);
    }
    function SubmitButton(p) {
      return h("button", { type: "submit", className: p.className || "btn btn-primary", disabled: !!(p.busy || p.disabled) }, p.busy ? [h("span", { key: "s", className: "hub-spin hub-spin-sm", "aria-hidden": "true" }), p.busyLabel || "Saving…"] : p.children);
    }
    function Field(p) {
      var id = p.id || ("hf_" + p.name);
      return h("div", { className: p.className || "col-12 col-md-6" },
        h("label", { className: "form-label", htmlFor: id }, p.label, p.required ? h("span", { className: "text-danger", "aria-hidden": "true" }, " *") : null),
        h("input", Object.assign({ id: id, name: p.name, type: p.type || "text", className: "form-control" + (p.error ? " is-invalid" : ""), value: p.value == null ? "" : p.value, required: !!p.required,
          "aria-invalid": p.error ? "true" : "false", "aria-describedby": id + "_msg", onChange: function (e) { p.onChange && p.onChange(e.target.value, e); } }, p.inputProps || {})),
        h("div", { className: "invalid-feedback", id: id + "_msg", role: "alert" }, p.error || ""));
    }
    function SelectField(p) {
      var id = p.id || ("hf_" + p.name);
      return h("div", { className: p.className || "col-12 col-md-6" },
        h("label", { className: "form-label", htmlFor: id }, p.label, p.required ? h("span", { className: "text-danger", "aria-hidden": "true" }, " *") : null),
        h("select", { id: id, name: p.name, className: "form-select" + (p.error ? " is-invalid" : ""), value: p.value == null ? "" : p.value, required: !!p.required, "aria-invalid": p.error ? "true" : "false",
          onChange: function (e) { p.onChange && p.onChange(e.target.value, e); } },
          h("option", { value: "" }, p.placeholder || "Select…"),
          (p.options || []).map(function (o) { return h("option", { key: o.value, value: o.value }, o.label); })),
        h("div", { className: "invalid-feedback", role: "alert" }, p.error || ""));
    }
    /* useSubmit(fn): one request at a time. run(...) resolves/rejects as fn does; state = {busy, error, success}. */
    function useSubmit(fn) {
      var s = React.useState({ busy: false, error: "", success: "" }), st = s[0], set = s[1], busy = React.useRef(false);
      var run = React.useCallback(function () {
        if (busy.current) return Promise.resolve(null);
        var args = arguments; busy.current = true; set({ busy: true, error: "", success: "" });
        return Promise.resolve().then(function () { return fn.apply(null, args); }).then(function (r) { busy.current = false; set({ busy: false, error: "", success: (r && r.message) || "Saved." }); return r; },
          function (e) { busy.current = false; set({ busy: false, error: (e && e.message) || "Something went wrong.", success: "" }); throw e; });
      }, [fn]);
      return { state: st, run: run };
    }
    Object.assign(window.SchoolHubForms, { React: React, FormStatus: FormStatus, SubmitButton: SubmitButton, Field: Field, SelectField: SelectField, useSubmit: useSubmit });

    /* ---------------------------------------------------------------- toast shown after a successful save + redirect */
    function Toasts(p) {
      var s = React.useState(p.items), items = s[0], set = s[1];
      React.useEffect(function () { var t = setTimeout(function () { set([]); }, 7000); return function () { clearTimeout(t); }; }, []);
      if (!items.length) return null;
      return h("div", { className: "hub-toast-root", role: "status", "aria-live": "polite" }, items.map(function (it, i) {
        return h("div", { key: i, className: "hub-toast alert alert-" + (it.kind === "warning" ? "warning" : "success") }, h("div", { className: "hub-status-body" }, it.text),
          h("button", { type: "button", className: "btn-close hub-status-x", "aria-label": "Dismiss", onClick: function () { set(items.filter(function (_, j) { return j !== i; })); } }));
      }));
    }
    try {
      var raw = sessionStorage.getItem("hubToast");
      if (raw) {
        sessionStorage.removeItem("hubToast");
        var items = JSON.parse(raw); var host = document.createElement("div"); document.body.appendChild(host);
        if (Array.isArray(items) && items.length) window.ReactDOM.createRoot(host).render(h(Toasts, { items: items.slice(0, 3) }));
      }
    } catch (e) { /* ignore */ }

    /* ---------------------------------------------------------------- per-form enhancer */
    function StatusHost(p) {
      var s = React.useState(null), st = s[0], set = s[1];
      React.useEffect(function () { p.register(set); }, []);
      return st ? h(FormStatus, Object.assign({}, st, { onClose: function () { set(null); } })) : null;
    }

    function controlsOf(form) {
      return [].filter.call(form.querySelectorAll("input,select,textarea"), function (el) {
        var t = (el.type || "").toLowerCase();
        return !el.disabled && t !== "hidden" && t !== "submit" && t !== "button" && t !== "reset" && t !== "image" && t !== "file" && el.name && !el.closest("[hidden]");
      });
    }
    function clearMark(el) { el.classList.remove("is-invalid"); el.removeAttribute("aria-invalid"); }
    function validate(form) {
      var problems = [], seenRadio = {};
      controlsOf(form).forEach(function (el) {
        var t = (el.type || "text").toLowerCase();
        if (t === "radio") {
          if (seenRadio[el.name]) return; seenRadio[el.name] = 1;
          var group = form.querySelectorAll('input[type="radio"][name="' + el.name.replace(/"/g, '\\"') + '"]');
          var req = [].some.call(group, function (r) { return r.required; }), any = [].some.call(group, function (r) { return r.checked; });
          if (req && !any) problems.push({ el: el, message: labelOf(el) + " is required." });
          return;
        }
        if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;   // not shown to the person (collapsed / hidden section): the server still validates it
        var match = el.getAttribute("data-match"), mv = null;
        if (match) { var other = form.querySelector(match); if (other) mv = other.value; }
        var msg = messageFor(labelOf(el), { value: el.value, type: t === "select-one" ? "select" : t, required: el.required, checked: el.checked, min: el.getAttribute("min"), max: el.getAttribute("max"),
          minlength: el.minLength > 0 ? el.minLength : 0, maxlength: el.maxLength > 0 ? el.maxLength : 0, pattern: el.getAttribute("pattern"), title: el.getAttribute("title"), matchValue: mv });
        if (msg) problems.push({ el: el, message: msg });
      });
      return problems;
    }

    function enhance(form) {
      var host = document.createElement("div"); host.className = "hub-status-host"; form.parentNode.insertBefore(host, form);
      var setStatus = function () {}, queued = null, busy = false, saved = new WeakMap();
      function status(s) { queued = s; setStatus(s); }
      window.ReactDOM.createRoot(host).render(h(StatusHost, { register: function (fn) { setStatus = fn; if (queued) fn(queued); } }));
      form.noValidate = true;
      form.addEventListener("input", function (e) { var el = e.target; if (el && el.classList && el.classList.contains("is-invalid") && el.closest("form") === form && !el.closest("[data-identity-fields],.identity-fields")) clearMark(el); });
      var buttons = function () { var id = form.id; return [].slice.call(form.querySelectorAll('button:not([type="button"]):not([type="reset"]),input[type="submit"]')).concat(id ? [].slice.call(document.querySelectorAll('button[form="' + id + '"]')) : []); };
      function lock(submitter) {
        buttons().forEach(function (b) { saved.set(b, { html: b.innerHTML, value: b.value, disabled: b.disabled }); b.disabled = true; });
        var main = submitter || buttons()[0];
        if (main && main.tagName === "BUTTON") main.innerHTML = '<span class="hub-spin hub-spin-sm" aria-hidden="true"></span>Saving…';
        form.setAttribute("aria-busy", "true");
      }
      function unlock() {
        buttons().forEach(function (b) { var s = saved.get(b); if (s) { if (b.tagName === "BUTTON") b.innerHTML = s.html; b.disabled = s.disabled; } });
        form.removeAttribute("aria-busy"); busy = false;
      }
      function fail(title, message, items) { unlock(); status({ kind: "error", title: title, message: message, items: items }); host.scrollIntoView && host.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
      window.addEventListener("pageshow", function (e) { if (e.persisted) unlock(); });

      function filename(resp) { var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(resp.headers.get("content-disposition") || ""); return m ? decodeURIComponent(m[1]) : "download"; }

      form.addEventListener("submit", function (e) {
        if (e.defaultPrevented) return;                          // another guard (e.g. the Date of Birth / Gender rule) already refused it
        e.preventDefault();
        if (busy) return;                                        // a save is already in flight: ignore double click / Enter
        var problems = validate(form);
        [].forEach.call(form.querySelectorAll(".is-invalid"), function (n) { if (!n.closest("[data-identity-fields],.identity-fields")) clearMark(n); });
        if (problems.length) {
          problems.forEach(function (p) { p.el.classList.add("is-invalid"); p.el.setAttribute("aria-invalid", "true"); });
          status({ kind: "invalid", title: problems.length === 1 ? "One thing needs your attention" : problems.length + " things need your attention", items: problems.slice(0, 8).map(function (p) { return p.message; }) });
          try { problems[0].el.focus({ preventScroll: false }); } catch (x) { /* ignore */ }
          return;
        }
        busy = true; status(null); lock(e.submitter);
        status({ kind: "loading", message: "Saving, please wait…" });
        var fd; try { fd = e.submitter ? new FormData(form, e.submitter) : new FormData(form); } catch (x) { fd = new FormData(form); if (e.submitter && e.submitter.name) fd.append(e.submitter.name, e.submitter.value); }
        fetch(form.getAttribute("action") || location.href, { method: "POST", body: fd, credentials: "same-origin", redirect: "follow", headers: { "X-Requested-With": "SchoolHubForms", "Accept": "text/html,application/json" } }).then(function (resp) {
          var path = ""; try { path = new URL(resp.url).pathname; } catch (x) { /* ignore */ }
          if (resp.redirected && /^\/(login|student-login|platform-login)\b/.test(path)) return fail("Session expired", "Your session has expired, so nothing was saved. Please sign in again, then repeat the entry.");
          var ct = (resp.headers.get("content-type") || "").toLowerCase();
          if (ct.indexOf("application/json") === 0) {
            return resp.json().catch(function () { return {}; }).then(function (j) {
              if (!resp.ok || j.ok === false) return fail("Not saved", j.error || statusMessage(resp.status));
              unlock(); status({ kind: "success", message: j.message || "Saved." });
            });
          }
          if (resp.ok && ct.indexOf("text/html") !== 0) {          // a file (CSV, PDF, Excel ...): download it, keep the page
            return resp.blob().then(function (b) { var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = filename(resp); document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500); unlock(); status({ kind: "success", message: "Your download has started." }); });
          }
          return resp.text().then(function (text) {
            if (!resp.ok) {
              var doc0 = new DOMParser().parseFromString(text, "text/html"), fl0 = readFlashes(doc0).filter(function (f) { return isErrorCat(f.cat); });
              return fail("Not saved", fl0.length ? fl0[0].text : statusMessage(resp.status), fl0.slice(1).map(function (f) { return f.text; }));
            }
            if (!resp.redirected) {                              // the server answered on the same URL: it re-rendered the page (with its own field errors or a result). Show exactly that.
              document.open(); document.write(text); document.close(); return;
            }
            var doc = new DOMParser().parseFromString(text, "text/html"), fl = readFlashes(doc);
            var errs = fl.filter(function (f) { return isErrorCat(f.cat); }), oks = fl.filter(function (f) { return !isErrorCat(f.cat); });
            if (errs.length) return fail("Not saved", errs[0].text, errs.slice(1).map(function (f) { return f.text; }));
            var toast = oks.length ? oks.map(function (f) { return { kind: f.cat === "warning" ? "warning" : "success", text: f.text }; }) : [{ kind: "success", text: "Saved." }];
            try { sessionStorage.setItem("hubToast", JSON.stringify(toast)); } catch (x) { /* storage blocked: the page reload below still shows the saved state */ }
            status({ kind: "success", message: toast[0].text });
            window.location.assign(resp.url || location.href);
          });
        }).catch(function () { fail("No connection", "Could not reach the server. Check your internet connection and try again. Nothing was saved."); });
      });
    }
    found.forEach(function (f) { try { enhance(f); } catch (x) { /* a form that cannot be enhanced keeps working as a normal form */ f.noValidate = false; } });
  }).catch(function () { /* CDN blocked: every form still posts normally and the Flask backend validates it */ });
})();
