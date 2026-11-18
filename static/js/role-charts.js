/* V109: draws the role-specific dashboard charts (partials/role_charts.html). Real data only (specs are built on the server).
   - bar / line / doughnut from one spec; integer axes for counts; readable labels, legends and tooltips;
   - follows light / dark ("sh-theme-change") and the person's text size ("sh-font-change");
   - window.schoolHubRoleCharts.update(specs) redraws in place (used by the React term / class filter). */
(function () {
  "use strict";
  var PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#0ea5e9", "#8b5cf6", "#ef4444", "#14b8a6", "#f97316", "#64748b"];
  var DONUT = ["#10b981", "#ef4444", "#94a3b8", "#6366f1"];
  var registry = {};
  function dark() { return document.documentElement.getAttribute("data-bs-theme") === "dark"; }
  function ink() { return dark() ? "#cbd5e1" : "#475569"; }
  function grid() { return dark() ? "rgba(148,163,184,.2)" : "#e8edf3"; }
  function fsize() { return Math.max(11, Math.round(parseFloat(getComputedStyle(document.documentElement).fontSize) * 0.78)); }

  function options(spec) {
    var f = fsize(), multi = spec.datasets.length > 1;
    if (spec.type === "doughnut") return { responsive: true, maintainAspectRatio: false, cutout: "58%",
      plugins: { legend: { position: "bottom", labels: { color: ink(), font: { size: f }, boxWidth: 12 } }, tooltip: { bodyFont: { size: f }, titleFont: { size: f } } } };
    return { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: { x: { stacked: !!spec.stacked, grid: { display: false }, ticks: { color: ink(), font: { size: f }, maxRotation: 50, autoSkip: true } },
                y: { stacked: !!spec.stacked, beginAtZero: true, grid: { color: grid() }, ticks: { color: ink(), font: { size: f }, precision: 0 } } },
      plugins: { legend: { display: multi, position: "top", labels: { color: ink(), font: { size: f }, boxWidth: 12 } }, tooltip: { bodyFont: { size: f }, titleFont: { size: f } } } };
  }
  function datasets(spec) {
    return spec.datasets.map(function (d, i) {
      if (spec.type === "doughnut") return { label: d.label, data: d.data, backgroundColor: DONUT.slice(0, d.data.length), borderWidth: 0 };
      var c = PALETTE[i % PALETTE.length];
      return spec.type === "line" ? { label: d.label, data: d.data, borderColor: c, backgroundColor: c + "33", fill: true, tension: 0.3, pointRadius: 3 }
                                  : { label: d.label, data: d.data, backgroundColor: c, borderRadius: 4, maxBarThickness: 46 };
    });
  }
  function draw(spec) {
    var canvas = document.getElementById(spec.id); if (!canvas || typeof window.Chart === "undefined") return;
    var card = canvas.closest(".rc-card"), body = canvas.closest(".rc-body"), empty = card && card.querySelector(".rc-empty");
    if (spec.empty) { if (registry[spec.id]) { registry[spec.id].destroy(); delete registry[spec.id]; } if (body) body.hidden = true; if (empty) { empty.textContent = spec.empty; empty.hidden = false; } return; }
    if (body) body.hidden = false; if (empty) empty.hidden = true;
    canvas.setAttribute("data-rc-spec", JSON.stringify(spec));
    var cfg = { type: spec.type, data: { labels: spec.labels, datasets: datasets(spec) }, options: options(spec) };
    if (registry[spec.id]) { var c = registry[spec.id]; c.data = cfg.data; c.options = cfg.options; c.update(); } else registry[spec.id] = new Chart(canvas, cfg);
  }
  function specOf(canvas) { try { return JSON.parse(canvas.getAttribute("data-rc-spec")); } catch (e) { return null; } }
  function all() { document.querySelectorAll("canvas[data-rc-spec]").forEach(function (c) { var s = specOf(c); if (s) draw(s); }); }
  window.schoolHubRoleCharts = { update: function (specs) { (specs || []).forEach(draw); }, redraw: all, registry: registry };
  function redrawAll() { Object.keys(registry).forEach(function (id) { var c = document.getElementById(id), s = c && specOf(c); if (s) { registry[id].options = options(s); registry[id].update(); } }); }
  window.addEventListener("sh-theme-change", redrawAll); window.addEventListener("sh-font-change", redrawAll);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", all); else all();
})();
