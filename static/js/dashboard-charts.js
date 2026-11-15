/* V95/V106: shared Chart.js rendering for the dashboard analytics charts (Student/Class Performance, Attendance Trend, Enrolment by
   Class Level, Academic Performance trend, Subject bars, and the older Gender donut where a page still has its canvas).
   Each dashboard embeds its server-rendered data as small JSON arrays and calls window.schoolHubDashboardCharts(data) once.

   V106 changes (behaviour of the first call is unchanged):
   - every chart is created OR updated in place through upsert(), keyed by its canvas id, so the React term / class filter can call
     window.schoolHubDashboardCharts.update(newData) and the charts redraw WITHOUT a page reload (no destroy/recreate flicker);
   - a chart whose data comes back empty is cleared and replaced by a short note, and comes back when data returns;
   - axis, grid and legend colours follow the light / dark theme and are re-applied on the "sh-theme-change" event. */
(function () {
  "use strict";

  var COLOR_AVG = "#6366f1", COLOR_PASS = "#10b981", COLOR_MALE = "#6366f1", COLOR_FEMALE = "#ec4899", COLOR_LINE = "#7c3aed";
  var COLOR_ENROLMENT = ["#818cf8", "#6366f1", "#4f46e5", "#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6"];
  var registry = {};   // canvas id -> Chart instance

  function haveChartJs() { return typeof window.Chart !== "undefined"; }
  function el(id) { return document.getElementById(id); }
  function isDark() { return document.documentElement.getAttribute("data-bs-theme") === "dark"; }
  function ink() { return isDark() ? "#c7d2e3" : "#475569"; }
  function grid() { return isDark() ? "rgba(148,163,184,.18)" : "#f1f5f9"; }

  function growWrap(canvas, count, perItem, minPx) {
    var wrap = canvas.parentElement;
    if (!wrap || !wrap.classList.contains("chart-wrap")) return;
    var scroller = wrap.parentElement;
    var avail = (scroller && scroller.classList.contains("chart-scroll")) ? scroller.clientWidth : wrap.clientWidth;
    var natural = Math.max(minPx || 0, (count || 0) * (perItem || 70));
    wrap.style.width = natural > avail ? natural + "px" : "100%";
  }

  function scales(max) {
    var y = { beginAtZero: true, grid: { color: grid() }, ticks: { color: ink() } };
    if (max) y.max = max;
    return { y: y, x: { grid: { display: false }, ticks: { color: ink() } } };
  }
  function opts(extra) {
    var o = { responsive: true, maintainAspectRatio: false, scales: scales(), plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 }, color: ink() } } } };
    return Object.assign(o, extra || {});
  }

  function note(canvas, show) {
    var wrap = canvas.closest(".chart-scroll") || canvas.parentElement;
    var n = wrap.parentElement && wrap.parentElement.querySelector(':scope > .chart-empty[data-for="' + canvas.id + '"]');
    if (show && !n && wrap.parentElement) {
      n = document.createElement("p");
      n.className = "muted chart-empty"; n.setAttribute("data-for", canvas.id);
      n.textContent = "No data for this selection yet.";
      wrap.parentElement.insertBefore(n, wrap.nextSibling);
    }
    if (n) n.hidden = !show;
    wrap.style.display = show ? "none" : "";
  }

  function upsert(id, labels, cfg) {
    var c = el(id);
    if (!c) return;
    var has = labels && labels.length;
    if (!has) {
      if (registry[id]) { registry[id].destroy(); delete registry[id]; }
      // never hide a canvas on the very first paint when the page rendered no data for it (that was the original behaviour: skip)
      if (c.dataset.sawData || registry[id] === undefined && c.dataset.filtered) note(c, true);
      return;
    }
    c.dataset.sawData = "1"; note(c, false);
    if (registry[id]) {
      var ch = registry[id];
      ch.data = cfg.data; ch.options = cfg.options; ch.update();
    } else {
      registry[id] = new Chart(c, cfg);
    }
  }

  function classPerformance(d) {
    var c = el("chartClassPerf"); if (!c) return;
    if (d.classLabels && d.classLabels.length) growWrap(c, d.classLabels.length, 72, 0);
    upsert("chartClassPerf", d.classLabels, { type: "bar", data: { labels: d.classLabels, datasets: [
      { label: "Average %", data: d.classAvg, backgroundColor: COLOR_AVG, borderRadius: 4 },
      { label: "Pass Rate %", data: d.classPass, backgroundColor: COLOR_PASS, borderRadius: 4 }] }, options: opts({ scales: scales(100) }) });
  }
  function genderDonut(d) {
    var c = el("chartGender"); if (!c) return;
    upsert("chartGender", ["Male", "Female"], { type: "doughnut", data: { labels: ["Male", "Female"],
      datasets: [{ data: [d.genderBoys || 0, d.genderGirls || 0], backgroundColor: [COLOR_MALE, COLOR_FEMALE], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 }, color: ink() } } } } });
  }
  function attendance(d) {
    upsert("chartAttendance", d.attendanceLabels, { type: "line", data: { labels: d.attendanceLabels, datasets: [
      { label: "Attendance %", data: d.attendanceRate, borderColor: COLOR_LINE, backgroundColor: "rgba(124,58,237,.12)", fill: true, tension: 0.35, pointRadius: 3 }] },
      options: opts({ scales: scales(100), plugins: { legend: { display: false } } }) });
  }
  function enrolment(d) {
    var c = el("chartEnrolment"); if (!c) return;
    if (d.enrolmentLabels && d.enrolmentLabels.length) growWrap(c, d.enrolmentLabels.length, 64, 0);
    upsert("chartEnrolment", d.enrolmentLabels, { type: "bar", data: { labels: d.enrolmentLabels, datasets: [
      { label: "Students", data: d.enrolmentCount, backgroundColor: COLOR_ENROLMENT, borderRadius: 4 }] }, options: opts({ plugins: { legend: { display: false } } }) });
  }
  function academicTrend(d) {
    var c = el("chartAcademicTrend"); if (!c) return;
    if (d.academicLabels && d.academicLabels.length) growWrap(c, d.academicLabels.length, 70, 0);
    var ds = [{ label: "My average %", data: d.academicMine, borderColor: COLOR_LINE, backgroundColor: "rgba(124,58,237,.12)", fill: true, tension: 0.35, pointRadius: 3 }];
    if (d.academicClassAvg && d.academicClassAvg.some(function (v) { return v !== null && v !== undefined; })) {
      ds.push({ label: "Class average %", data: d.academicClassAvg, borderColor: "#94a3b8", borderDash: [5, 4], pointRadius: 2, fill: false, tension: 0.35 });
    }
    upsert("chartAcademicTrend", d.academicLabels, { type: "line", data: { labels: d.academicLabels, datasets: ds }, options: opts({ scales: scales(100) }) });
  }
  function subjectBar(d) {
    var c = el("chartSubjectScores"); if (!c) return;
    if (d.subjectLabels && d.subjectLabels.length) growWrap(c, d.subjectLabels.length, 60, 0);
    upsert("chartSubjectScores", d.subjectLabels, { type: "bar", data: { labels: d.subjectLabels, datasets: [
      { label: "Score", data: d.subjectScores, backgroundColor: COLOR_AVG, borderRadius: 4 }] }, options: opts({ plugins: { legend: { display: false } } }) });
  }

  function draw(d) {
    if (!haveChartJs() || !d) return;
    classPerformance(d); genderDonut(d); attendance(d); enrolment(d); academicTrend(d); subjectBar(d);
  }

  window.schoolHubDashboardCharts = function (d) { draw(d); };
  /* V106: called by the React dashboard filter with fresh data; marks the canvases as "filtered" so an empty result shows a note */
  window.schoolHubDashboardCharts.update = function (d) {
    ["chartClassPerf", "chartAttendance", "chartEnrolment"].forEach(function (id) { var c = el(id); if (c) c.dataset.filtered = "1"; });
    draw(d);
  };
  window.schoolHubDashboardCharts.registry = registry;
  window.addEventListener("sh-theme-change", function () {
    if (!haveChartJs()) return;
    Object.keys(registry).forEach(function (id) {
      var ch = registry[id], o = ch.options || {};
      if (o.scales) Object.keys(o.scales).forEach(function (k) {
        var s = o.scales[k]; if (s.ticks) s.ticks.color = ink(); if (s.grid && s.grid.display !== false) s.grid.color = grid();
      });
      if (o.plugins && o.plugins.legend && o.plugins.legend.labels) o.plugins.legend.labels.color = ink();
      ch.update();
    });
  });
})();
