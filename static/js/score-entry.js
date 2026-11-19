/* V106: React score-entry grid for subject teachers (CA1 / CA2 / [CA3] / Exam).
   - totals and grades recalculate on every keystroke (grade bands come from the school's Grading page);
   - every box is validated against its maximum instantly (red box + message); an invalid row can never be sent;
   - each row saves on its own, with its own status chip (Unsaved / Saving / Saved / Error / Locked), WITHOUT a page reload:
       * when focus leaves a row that has valid changes  (not per keystroke, so the audit trail only records finished values)
       * the row's own Save button, or "Save all changes" / Ctrl+S
     The server (POST /api/scores/<class>/<subject>/row) re-validates, applies the same permission / lock / reason rules and
     audit trail as the classic form, and returns the authoritative total and grade, which replace the live estimate;
   - Enter moves down the same column; a search box filters the list; leaving the page with unsaved rows asks first.
   The classic server-rendered form stays on the page as the no-JavaScript fallback and is removed only once this grid is running. */
(function () {
  "use strict";
  var UI = window.SchoolHubUI; if (!UI) return;
  var React = UI.React, h = UI.h, useReducer = React.useReducer, useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useCallback = React.useCallback, useMemo = React.useMemo;
  var host = document.getElementById("scoreApp"); if (!host) return;
  var boot; try { boot = JSON.parse(host.getAttribute("data-config")); } catch (e) { return; }

  var FIELDS = boot.fields;                       // [{key:'ca1', label:'CA1', max:20}, ...]
  var SAVE_URL = boot.save_url, CSRF = boot.csrf;

  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function round2(n) { return Math.round(n * 100) / 100; }
  function fmt(n) { return String(round2(n)); }
  function clean(raw) { raw = String(raw).replace(/,/g, "."); var m = raw.match(/^\d*\.?\d{0,2}/); return m ? m[0] : ""; }
  function fieldError(f, v) {
    v = String(v).trim(); if (v === "") return "";
    var n = Number(v); if (!isFinite(n) || n < 0) return "Enter a number from 0 to " + f.max;
    return n > f.max ? "Maximum is " + f.max : "";
  }
  function rowErrors(vals) { var e = {}; FIELDS.forEach(function (f) { var m = fieldError(f, vals[f.key]); if (m) e[f.key] = m; }); return e; }
  function totalOf(vals) { return round2(FIELDS.reduce(function (s, f) { return s + num(vals[f.key]); }, 0)); }
  function gradeOf(total) {
    for (var i = 0; i < boot.bands.length; i++) { var b = boot.bands[i]; if (total >= b.min_score && total <= b.max_score) return { grade: b.grade, remark: b.remark }; }
    return { grade: "-", remark: "-" };
  }
  function snapshot(vals) { var o = {}; FIELDS.forEach(function (f) { o[f.key] = String(vals[f.key]).trim(); }); return o; }
  function sameVals(a, b) { return FIELDS.every(function (f) { return String(a[f.key]).trim() === String(b[f.key]).trim(); }); }

  function init() {
    var rows = {}, order = [];
    boot.students.forEach(function (s) {
      var vals = {}; FIELDS.forEach(function (f) { vals[f.key] = s[f.key] === null || s[f.key] === undefined ? "" : String(s[f.key]); });
      var t = totalOf(vals), g = s.has_row ? gradeOf(t) : { grade: "", remark: "" };
      rows[s.id] = { id: s.id, adm: s.adm, name: s.name, vals: vals, saved: snapshot(vals), status: "clean", msg: "", total: s.has_row ? t : null, grade: g.grade, remark: g.remark, rev: 0, at: "" };
      order.push(s.id);
    });
    return { rows: rows, order: order, locked: !!boot.lock.locked, lockLabel: boot.lock.label, needReason: false };
  }

  function reducer(st, a) {
    var r = st.rows[a.id], rows;
    switch (a.type) {
      case "edit": {
        var vals = Object.assign({}, r.vals); vals[a.field] = a.value;
        var dirty = !sameVals(vals, r.saved), t = totalOf(vals), g = gradeOf(t);
        rows = Object.assign({}, st.rows); rows[a.id] = Object.assign({}, r, { vals: vals, total: t, grade: g.grade, remark: g.remark, rev: r.rev + 1,
          status: dirty ? (Object.keys(rowErrors(vals)).length ? "invalid" : "dirty") : "clean", msg: "" });
        return Object.assign({}, st, { rows: rows });
      }
      case "saving": rows = Object.assign({}, st.rows); rows[a.id] = Object.assign({}, r, { status: "saving", msg: "" }); return Object.assign({}, st, { rows: rows });
      case "saved": {
        rows = Object.assign({}, st.rows);
        var unchanged = r.rev === a.rev;           // nothing was typed while the request was in flight
        rows[a.id] = Object.assign({}, r, { saved: a.snap, status: unchanged ? "saved" : (Object.keys(rowErrors(r.vals)).length ? "invalid" : "dirty"), msg: "",
          total: unchanged ? a.total : r.total, grade: unchanged ? a.grade : r.grade, remark: unchanged ? a.remark : r.remark, at: a.at });
        return Object.assign({}, st, { rows: rows, needReason: false });
      }
      case "error": rows = Object.assign({}, st.rows); rows[a.id] = Object.assign({}, r, { status: "error", msg: a.msg }); return Object.assign({}, st, { rows: rows, needReason: st.needReason || !!a.needReason });
      case "locked": return Object.assign({}, st, { locked: true, lockLabel: a.label || st.lockLabel });
      default: return st;
    }
  }

  var CHIP = { clean: ["", ""], dirty: ["Unsaved", "text-bg-warning"], invalid: ["Fix errors", "text-bg-danger"], saving: ["Saving…", "text-bg-info"], saved: ["Saved", "text-bg-success"], error: ["Not saved", "text-bg-danger"] };

  var Row = React.memo(function Row(p) {
    var r = p.row, errs = rowErrors(r.vals), chip = CHIP[r.status] || CHIP.clean;
    var hasAny = r.total !== null || FIELDS.some(function (f) { return String(r.vals[f.key]).trim() !== ""; });
    return h("tr", { "data-row": r.id, className: r.status === "error" || r.status === "invalid" ? "table-danger" : "", onBlur: function (e) {
        if (!e.currentTarget.contains(e.relatedTarget)) p.onLeave(r.id);
      } },
      h("td", { className: "text-nowrap" }, r.adm),
      h("td", null, r.name),
      FIELDS.map(function (f) {
        var bad = errs[f.key];
        return h("td", { key: f.key, style: { minWidth: "5.5rem" } },
          h("input", { type: "text", inputMode: "decimal", autoComplete: "off", className: "form-control form-control-sm text-end" + (bad ? " is-invalid" : ""), value: r.vals[f.key],
            disabled: p.locked, "aria-label": r.name + " " + f.label + " (maximum " + f.max + ")", "aria-invalid": bad ? "true" : "false", title: bad || "", "data-r": r.id, "data-f": f.key,
            onChange: function (e) { p.dispatch({ type: "edit", id: r.id, field: f.key, value: clean(e.target.value) }); },
            onFocus: function (e) { e.target.select(); },
            onKeyDown: function (e) { if (e.key === "Enter") { e.preventDefault(); p.onEnter(e.target, r.id, f.key); } } }),
          bad && h("div", { className: "invalid-feedback d-block small" }, bad));
      }),
      h("td", { className: "fw-bold text-end" }, hasAny ? fmt(r.total === null ? totalOf(r.vals) : r.total) : "–"),
      h("td", { className: "text-center" }, hasAny ? h("span", { className: "badge bg-body-secondary text-body border", title: r.remark || "" }, r.grade || "–") : "–"),
      h("td", { className: "text-nowrap", style: { minWidth: "9.5rem" } },
        chip[0] ? h("span", { className: "badge " + chip[1], role: "status" }, chip[0]) : null,
        r.status === "saved" && r.at ? h("small", { className: "muted ms-1" }, r.at) : null,
        (r.status === "dirty" || r.status === "error") && !p.locked ? h("button", { type: "button", className: "btn btn-primary btn-sm ms-2 py-0", onClick: function () { p.onSave(r.id); } }, "Save") : null,
        r.msg ? h("div", { className: "small text-danger mt-1" }, r.msg) : null));
  });

  function App() {
    var s0 = useReducer(reducer, null, init), st = s0[0], dispatch = s0[1];
    var s1 = useState(""), query = s1[0], setQuery = s1[1];
    var s2 = useState(""), reason = s2[0], setReason = s2[1];
    var s3 = useState(false), bulk = s3[0], setBulk = s3[1];
    var stRef = useRef(st); stRef.current = st; var reasonRef = useRef(reason); reasonRef.current = reason;
    var inflight = useRef({});

    var saveRow = useCallback(function (id) {
      var cur = stRef.current, r = cur.rows[id];
      if (!r || cur.locked || inflight.current[id]) return Promise.resolve();
      if (!(r.status === "dirty" || r.status === "error")) return Promise.resolve();
      if (Object.keys(rowErrors(r.vals)).length) { dispatch({ type: "edit", id: id, field: FIELDS[0].key, value: r.vals[FIELDS[0].key] }); return Promise.resolve(); }
      inflight.current[id] = true; var rev = r.rev, snap = snapshot(r.vals);
      dispatch({ type: "saving", id: id });
      var body = { student_id: id, reason: reasonRef.current }; FIELDS.forEach(function (f) { body[f.key] = r.vals[f.key]; });
      return UI.api(SAVE_URL, { body: body, csrf: CSRF }).then(function (p) {
        dispatch({ type: "saved", id: id, rev: rev, snap: snap, total: p.total, grade: p.grade, remark: p.remark, at: p.saved_at });
      }).catch(function (e) {
        if (e.status === 423) dispatch({ type: "locked", label: "" });
        dispatch({ type: "error", id: id, msg: e.message, needReason: !!(e.payload && e.payload.needs_reason) });
      }).then(function () { inflight.current[id] = false; });
    }, []);

    var onLeave = useCallback(function (id) { saveRow(id); }, [saveRow]);
    var onEnter = useCallback(function (input, id, key) {
      var tr = input.closest("tr"), next = tr && tr.nextElementSibling;
      while (next && !next.querySelector('[data-f="' + key + '"]')) next = next.nextElementSibling;
      var target = next && next.querySelector('[data-f="' + key + '"]');
      if (target) target.focus(); else input.blur();
    }, []);

    var pending = st.order.filter(function (id) { var s = st.rows[id].status; return s === "dirty" || s === "error"; });
    var invalid = st.order.filter(function (id) { return st.rows[id].status === "invalid"; });
    var saveAll = useCallback(function () {
      setBulk(true);
      var ids = stRef.current.order.filter(function (id) { var s = stRef.current.rows[id].status; return s === "dirty" || s === "error"; });
      return ids.reduce(function (chain, id) { return chain.then(function () { return saveRow(id); }); }, Promise.resolve()).then(function () { setBulk(false); });
    }, [saveRow]);

    useEffect(function () {
      var key = function (e) { if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) { e.preventDefault(); saveAll(); } };
      var leave = function (e) {
        var busy = Object.keys(stRef.current.rows).some(function (id) { var s = stRef.current.rows[id].status; return s === "dirty" || s === "saving" || s === "invalid" || s === "error"; });
        if (busy) { e.preventDefault(); e.returnValue = ""; }
      };
      window.addEventListener("keydown", key); window.addEventListener("beforeunload", leave);
      return function () { window.removeEventListener("keydown", key); window.removeEventListener("beforeunload", leave); };
    }, [saveAll]);

    var q = query.trim().toLowerCase();
    var visible = st.order.filter(function (id) { var r = st.rows[id]; return !q || (r.adm + " " + r.name).toLowerCase().indexOf(q) !== -1; });
    var entered = st.order.filter(function (id) { var r = st.rows[id]; return r.total !== null || FIELDS.some(function (f) { return String(r.vals[f.key]).trim() !== ""; }); });
    var totals = entered.map(function (id) { var r = st.rows[id]; return r.total === null ? totalOf(r.vals) : r.total; });
    var avg = totals.length ? round2(totals.reduce(function (a, b) { return a + b; }, 0) / totals.length) : null;

    return h("div", { className: "score-grid" },
      st.locked && h("div", { className: "alert alert-warning", role: "alert" }, h("b", null, "Scores are locked. "), "This class's result is “" + st.lockLabel + "”, so scores cannot be changed here."),
      h("div", { className: "card p-3 mb-3" },
        h("div", { className: "row g-3 align-items-end" },
          h("div", { className: "col-12 col-md-5" }, h("label", { className: "form-label mb-1", htmlFor: "seSearch" }, "Search students"),
            h("input", { id: "seSearch", type: "search", className: "form-control", placeholder: "Type a name or Admission No. / Register No.", autoComplete: "off", value: query, onChange: function (e) { setQuery(e.target.value); } })),
          h("div", { className: "col-12 col-md-7" }, h("label", { className: "form-label mb-1", htmlFor: "seReason" }, "Reason for change ", h("span", { className: "muted" }, "(required once results are published)")),
            h("input", { id: "seReason", type: "text", maxLength: 300, className: "form-control" + (st.needReason && !reason.trim() ? " is-invalid" : ""), placeholder: "e.g. Score correction", value: reason, onChange: function (e) { setReason(e.target.value); } })))),
      h("div", { className: "d-flex flex-wrap gap-2 align-items-center mb-2 score-summary" },
        h("span", { className: "badge bg-body-secondary text-body border" }, "Entered " + entered.length + " / " + st.order.length),
        avg !== null && h("span", { className: "badge bg-body-secondary text-body border" }, "Average " + avg),
        totals.length > 0 && h("span", { className: "badge bg-body-secondary text-body border" }, "High " + Math.max.apply(null, totals) + " · Low " + Math.min.apply(null, totals)),
        invalid.length > 0 && h("span", { className: "badge text-bg-danger" }, invalid.length + " row" + (invalid.length === 1 ? "" : "s") + " need fixing"),
        h("span", { className: "ms-auto d-flex align-items-center gap-2" },
          h("span", { className: "small muted", "aria-live": "polite" }, pending.length ? pending.length + " unsaved" : "All changes saved"),
          h("button", { type: "button", className: "btn btn-primary", disabled: st.locked || bulk || !pending.length, onClick: saveAll }, bulk ? "Saving…" : "Save all changes"))),
      h("div", { className: "table-responsive" },
        h("table", { className: "table table-sm table-hover align-middle", id: "scoreTable" },
          h("thead", null, h("tr", null, h("th", null, "Adm / Reg No."), h("th", null, "Student"),
            FIELDS.map(function (f) { return h("th", { key: f.key, className: "text-end" }, f.label, h("br"), h("small", { className: "muted" }, "max " + f.max)); }),
            h("th", { className: "text-end" }, "Total"), h("th", { className: "text-center" }, "Grade"), h("th", null, "Status"))),
          h("tbody", null, visible.map(function (id) { return h(Row, { key: id, row: st.rows[id], locked: st.locked, dispatch: dispatch, onLeave: onLeave, onSave: saveRow, onEnter: onEnter }); })))),
      !visible.length && h("p", { className: "muted" }, "No student matches “" + query + "”."),
      h("p", { className: "small muted" }, "Rows save when you move to another row. Press Enter to go down a column, or Ctrl+S to save everything."));
  }

  var fallback = document.getElementById("scoreFallback");
  UI.mount(host, h(App));
  if (fallback) fallback.remove();
})();
