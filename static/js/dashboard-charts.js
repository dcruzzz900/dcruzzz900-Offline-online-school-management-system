/* V95: shared Chart.js rendering for the Admin/Teacher/Student/Parent dashboard analytics
   charts (Student/Class Performance, Gender Distribution, Attendance Trend, Enrolment by Class
   Level, Academic Performance trend). Each dashboard template embeds its own server-rendered
   data as small JSON arrays, then calls one of the functions below with whichever canvases are
   actually present on that page -- a canvas a given role's dashboard doesn't render (e.g. no
   Gender Distribution on the Student dashboard) is simply skipped, never an error. */
(function () {
  "use strict";

  var COLOR_AVG = "#6366f1";       // indigo -- "Average %" bars
  var COLOR_PASS = "#10b981";      // green -- "Pass Rate %" bars
  var COLOR_MALE = "#6366f1";      // indigo -- gender donut, Male
  var COLOR_FEMALE = "#ec4899";    // pink -- gender donut, Female
  var COLOR_LINE = "#7c3aed";      // purple -- attendance / academic trend lines
  var COLOR_ENROLMENT = ["#818cf8", "#6366f1", "#4f46e5", "#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6"];

  function haveChartJs() {
    return typeof window.Chart !== "undefined";
  }

  function el(id) {
    return document.getElementById(id);
  }

  // V96: charts were rendering oversized/"verbose" because the canvases had no height-
  // constrained parent, so Chart.js's responsive resize had nothing stable to measure against.
  // Every chart now lives inside a fixed-height .chart-wrap (set in CSS), which fixes that. For
  // charts whose category count can grow (more classes, more subjects), growWrap() widens that
  // wrap -- inside a horizontally scrollable .chart-scroll -- so bars stay readably spaced
  // instead of being squeezed into a fixed width; the chart only grows, it never balloons in
  // height, which is what made the old version feel so large.
  function growWrap(canvas, count, perItem, minPx) {
    var wrap = canvas.parentElement;
    if (!wrap || !wrap.classList.contains("chart-wrap")) return;
    var scroller = wrap.parentElement;
    var avail = (scroller && scroller.classList.contains("chart-scroll")) ? scroller.clientWidth : wrap.clientWidth;
    var natural = Math.max(minPx || 0, (count || 0) * (perItem || 70));
    wrap.style.width = natural > avail ? natural + "px" : "100%";
  }

  function commonGridOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, grid: { color: "#f1f5f9" } }, x: { grid: { display: false } } },
      plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } } },
    };
  }

  function renderClassPerformance(labels, avg, pass) {
    var c = el("chartClassPerf");
    if (!c || !labels || !labels.length) return;
    growWrap(c, labels.length, 72, 0);
    new Chart(c, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "Average %", data: avg, backgroundColor: COLOR_AVG, borderRadius: 4 },
          { label: "Pass Rate %", data: pass, backgroundColor: COLOR_PASS, borderRadius: 4 },
        ],
      },
      options: Object.assign(commonGridOptions(), { scales: { y: { beginAtZero: true, max: 100, grid: { color: "#f1f5f9" } }, x: { grid: { display: false } } } }),
    });
  }

  function renderGenderDonut(boys, girls) {
    var c = el("chartGender");
    if (!c) return;
    new Chart(c, {
      type: "doughnut",
      data: {
        labels: ["Male", "Female"],
        datasets: [{ data: [boys || 0, girls || 0], backgroundColor: [COLOR_MALE, COLOR_FEMALE], borderWidth: 0 }],
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } } },
    });
  }

  function renderAttendanceTrend(labels, rate) {
    var c = el("chartAttendance");
    if (!c || !labels || !labels.length) return;
    new Chart(c, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{ label: "Attendance %", data: rate, borderColor: COLOR_LINE, backgroundColor: "rgba(124,58,237,.12)", fill: true, tension: 0.35, pointRadius: 3 }],
      },
      options: Object.assign(commonGridOptions(), { scales: { y: { beginAtZero: true, max: 100, grid: { color: "#f1f5f9" } }, x: { grid: { display: false } } }, plugins: { legend: { display: false } } }),
    });
  }

  function renderEnrolment(labels, counts) {
    var c = el("chartEnrolment");
    if (!c || !labels || !labels.length) return;
    growWrap(c, labels.length, 64, 0);
    new Chart(c, {
      type: "bar",
      data: { labels: labels, datasets: [{ label: "Students", data: counts, backgroundColor: COLOR_ENROLMENT, borderRadius: 4 }] },
      options: Object.assign(commonGridOptions(), { plugins: { legend: { display: false } } }),
    });
  }

  function renderAcademicTrend(labels, mine, classAvg) {
    var c = el("chartAcademicTrend");
    if (!c || !labels || !labels.length) return;
    growWrap(c, labels.length, 70, 0);
    var datasets = [{ label: "My average %", data: mine, borderColor: COLOR_LINE, backgroundColor: "rgba(124,58,237,.12)", fill: true, tension: 0.35, pointRadius: 3 }];
    if (classAvg && classAvg.some(function (v) { return v !== null && v !== undefined; })) {
      datasets.push({ label: "Class average %", data: classAvg, borderColor: "#94a3b8", borderDash: [5, 4], pointRadius: 2, fill: false, tension: 0.35 });
    }
    new Chart(c, {
      type: "line",
      data: { labels: labels, datasets: datasets },
      options: Object.assign(commonGridOptions(), { scales: { y: { beginAtZero: true, max: 100, grid: { color: "#f1f5f9" } }, x: { grid: { display: false } } } }),
    });
  }

  function renderSubjectBar(labels, scores) {
    var c = el("chartSubjectScores");
    if (!c || !labels || !labels.length) return;
    growWrap(c, labels.length, 60, 0);
    new Chart(c, {
      type: "bar",
      data: { labels: labels, datasets: [{ label: "Score", data: scores, backgroundColor: COLOR_AVG, borderRadius: 4 }] },
      options: Object.assign(commonGridOptions(), { plugins: { legend: { display: false } } }),
    });
  }

  window.schoolHubDashboardCharts = function (d) {
    if (!haveChartJs() || !d) return;
    renderClassPerformance(d.classLabels, d.classAvg, d.classPass);
    renderGenderDonut(d.genderBoys, d.genderGirls);
    renderAttendanceTrend(d.attendanceLabels, d.attendanceRate);
    renderEnrolment(d.enrolmentLabels, d.enrolmentCount);
    renderAcademicTrend(d.academicLabels, d.academicMine, d.academicClassAvg);
    renderSubjectBar(d.subjectLabels, d.subjectScores);
  };
})();
