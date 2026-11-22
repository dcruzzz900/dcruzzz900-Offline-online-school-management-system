/* V112: lets the existing class / term filter (React, dashboard-filters.js) redraw the v106 Subject Performance and Pass/Fail panels.
   dashboard-filters.js calls window.schoolHubRoleCharts.update(specs) with the same data the old canvas charts used. */
(function () {
  function esc(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function subjects(spec) {
    var host = document.querySelector('#subject-performance [data-rc-body]'); if (!host) return;
    var labels = spec.labels || [], data = (spec.datasets && spec.datasets[0] && spec.datasets[0].data) || [];
    if (!labels.length) { host.innerHTML = '<p style="padding:16px;color:var(--mut);font-size:.85rem">No scores recorded for this selection yet.</p>'; return; }
    host.innerHTML = labels.map(function (n, i) { var v = Number(data[i]) || 0, c = v >= 70 ? 'g-a' : v >= 50 ? 'g-b' : 'g-c';
      return '<div class="grade-row"><div class="grade-row-top"><b>' + esc(n) + '</b><span>' + v + '% avg</span></div><div class="grade-bar ' + c + '"><i style="width:' + Math.min(v, 100) + '%"></i></div></div>'; }).join('');
  }
  function passfail(spec) {
    var host = document.querySelector('#pass-fail [data-rc-body]'); if (!host) return;
    var d = (spec.datasets && spec.datasets[0] && spec.datasets[0].data) || [0, 0, 0], p = +d[0] || 0, f = +d[1] || 0, n = +d[2] || 0, t = p + f + n, C = 301.6;
    if (!t) { host.innerHTML = '<p style="padding:16px;color:var(--mut);font-size:.85rem">No students for this selection.</p>'; return; }
    var a1 = C * p / t, a2 = C * f / t, a3 = C * n / t;
    function ring(col, len, off) { return '<circle cx="60" cy="60" r="48" fill="none" stroke="' + col + '" stroke-width="16" stroke-dasharray="' + len.toFixed(1) + ' ' + C + '"' + (off ? ' stroke-dashoffset="-' + off.toFixed(1) + '"' : '') + ' transform="rotate(-90 60 60)"/>'; }
    host.innerHTML = '<div class="donut-wrap"><svg viewBox="0 0 120 120" width="120" height="120" role="img" aria-label="' + p + ' passed, ' + f + ' failed, ' + n + ' not yet assessed"><circle cx="60" cy="60" r="48" fill="none" stroke="#f1f5f9" stroke-width="16" class="pf-track"/>' +
      ring('#27c25a', a1, 0) + ring('#ef4444', a2, a1) + ring('#cbd5e1', a3, a1 + a2) + '<text x="60" y="56" text-anchor="middle" font-size="14" font-weight="800" class="pf-num">' + t + '</text><text x="60" y="72" text-anchor="middle" font-size="9" class="pf-lbl">students</text></svg>' +
      '<div class="donut-legend"><span><i class="dot-m" style="background:#27c25a"></i> Passed — ' + p + '</span><span><i class="dot-m" style="background:#ef4444"></i> Failed — ' + f + '</span><span><i class="dot-m" style="background:#cbd5e1"></i> Not yet assessed — ' + n + '</span></div></div>';
  }
  window.schoolHubRoleCharts = { update: function (specs) { (specs || []).forEach(function (s) { if (s.id === 'rcSubjects') subjects(s); else if (s.id === 'rcPassFail') passfail(s); }); }, redraw: function () {} };
})();
