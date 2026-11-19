/* V106: React term / class filter for the Chart.js dashboards (School Analytics, Teacher dashboard).
   React owns the CONTROLS and their state; on every change it asks /api/dashboard/analytics for the numbers, then
     - redraws the Chart.js charts in place (window.schoolHubDashboardCharts.update, no page reload),
     - swaps in the shared Gender Distribution panel and the Top Performing Students table (same server markup as the full page),
   and keeps the choice in the address bar (?term_id=&class_id=) so a reload or a shared link opens the same view. */
(function () {
  "use strict";
  var UI = window.SchoolHubUI; if (!UI) return;
  var React = UI.React, h = UI.h, useState = React.useState, useEffect = React.useEffect, useRef = React.useRef;
  var host = document.getElementById("dashFilters"); if (!host) return;
  var cfg = {}; try { cfg = JSON.parse(host.getAttribute("data-config") || "{}"); } catch (e) { return; }
  if (!cfg.url) return;

  function qs() { var p = new URLSearchParams(window.location.search); return { term: p.get("term_id"), cls: p.get("class_id") }; }
  function has(list, id, key) { return list.some(function (x) { return String(x[key || "id"]) === String(id); }); }

  function applyPayload(p) {
    var slot = function (n) { return document.querySelector('[data-slot="' + n + '"]'); };
    var g = slot("gender"); if (g && p.gender_html !== undefined) { g.innerHTML = p.gender_html; g.classList.remove("gp-loading"); }
    var t = slot("top-students"); if (t && p.top_students_html !== undefined) t.innerHTML = p.top_students_html;
    if (window.schoolHubDashboardCharts && window.schoolHubDashboardCharts.update) window.schoolHubDashboardCharts.update(p.charts || {});
    if (window.schoolHubRoleCharts && p.role_charts) window.schoolHubRoleCharts.update(p.role_charts);
    document.querySelectorAll("[data-scope-label]").forEach(function (n) { n.textContent = p.scope || ""; });
  }

  function Filters() {
    var init = qs();
    var s0 = useState(has(cfg.terms || [], init.term) ? String(init.term) : String(cfg.term_id || "")), termId = s0[0], setTermId = s0[1];
    var s1 = useState(init.cls && has(cfg.classes || [], init.cls) ? String(init.cls) : ""), classId = s1[0], setClassId = s1[1];
    var s2 = useState("idle"), status = s2[0], setStatus = s2[1];
    var s3 = useState(""), error = s3[0], setError = s3[1];
    var s4 = useState(""), summary = s4[0], setSummary = s4[1];
    var first = useRef(true), defaultTerm = String(cfg.term_id || "");

    useEffect(function () {
      var atDefault = termId === defaultTerm && classId === "";
      // the page was rendered for the default view: do not re-fetch it on mount
      if (first.current) { first.current = false; if (atDefault) return; }
      var ctl = new AbortController(); setStatus("loading"); setError("");
      var g = document.querySelector('[data-slot="gender"]'); if (g) g.classList.add("gp-loading");
      var params = new URLSearchParams(); if (termId) params.set("term_id", termId); if (classId) params.set("class_id", classId);
      UI.api(cfg.url + "?" + params.toString(), { signal: ctl.signal }).then(function (p) {
        applyPayload(p); setStatus("idle");
        setSummary((p.scope || "") + (p.term ? " · " + p.term.label : ""));
        var u = new URL(window.location.href); u.searchParams.delete("term_id"); u.searchParams.delete("class_id");
        if (!atDefault) { if (termId) u.searchParams.set("term_id", termId); if (classId) u.searchParams.set("class_id", classId); }
        window.history.replaceState(null, "", u.toString());
      }).catch(function (e) {
        if (e.name === "AbortError") return;
        setStatus("error"); setError(e.message || "Could not load this view.");
        if (g) g.classList.remove("gp-loading");
      });
      return function () { ctl.abort(); };
    }, [termId, classId]);

    var dirty = termId !== defaultTerm || classId !== "";
    return h("form", { className: "dash-filter-bar card p-3 mb-3", onSubmit: function (e) { e.preventDefault(); }, "aria-label": "Dashboard filters" },
      h("div", { className: "row g-2 align-items-end" },
        h("div", { className: "col-12 col-sm-6 col-lg-4" },
          h("label", { className: "form-label mb-1", htmlFor: "dfTerm" }, "Term"),
          h("select", { id: "dfTerm", className: "form-select", value: termId, onChange: function (e) { setTermId(e.target.value); } },
            (cfg.terms || []).map(function (t) { return h("option", { key: t.id, value: String(t.id) }, t.label); }))),
        h("div", { className: "col-12 col-sm-6 col-lg-4" },
          h("label", { className: "form-label mb-1", htmlFor: "dfClass" }, "Class"),
          h("select", { id: "dfClass", className: "form-select", value: classId, onChange: function (e) { setClassId(e.target.value); } },
            [h("option", { key: "all", value: "" }, cfg.all_label || "All classes")].concat(
              (cfg.classes || []).map(function (c) { return h("option", { key: c.id, value: String(c.id) }, c.name); })))),
        h("div", { className: "col-12 col-lg-4 d-flex align-items-center gap-2" },
          h("button", { type: "button", className: "btn btn-secondary", disabled: !dirty, onClick: function () { setTermId(defaultTerm); setClassId(""); } }, "Reset"),
          status === "loading" && h("span", { className: "spinner-border spinner-border-sm text-secondary", role: "status", "aria-label": "Loading" }),
          h("span", { className: "small muted", "aria-live": "polite" }, status === "loading" ? "Updating…" : summary))),
      error && h("div", { className: "alert alert-danger py-2 mt-2 mb-0", role: "alert" }, error));
  }
  UI.mount(host, h(Filters));
})();
