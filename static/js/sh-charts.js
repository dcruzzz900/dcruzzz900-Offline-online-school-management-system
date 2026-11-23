/* V112: tiny dependency-free SVG charts (work fully offline). Colours come from CSS variables, so dark mode is always readable.
   ShCharts.line(host, labels, values, {max, suffix, color, empty})  - values may contain null (= no record: a gap in the line)
   ShCharts.bars(host, labels, values, {colors, empty})
   Admin dashboard wiring: reads <script id="adChartsData" type="application/json"> and the [data-att-group] [data-att-range] [data-enrol-mode] buttons. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  function el(n, a, t) { var e = document.createElementNS(NS, n); for (var k in a) e.setAttribute(k, a[k]); if (t != null) e.textContent = t; return e; }
  function clear(h) { while (h.firstChild) h.removeChild(h.firstChild); }
  function msg(h, t) { clear(h); var p = document.createElement('p'); p.className = 'shc-empty'; p.textContent = t; h.appendChild(p); }
  function labelLines(svg, x, y, text, cls) { var parts = String(text).split(' · '), t = el('text', { x: x, y: y, 'text-anchor': 'middle', 'class': cls });
    parts.forEach(function (p, i) { t.appendChild(el('tspan', { x: x, dy: i ? 11 : 0 }, p)); }); svg.appendChild(t); }
  function nice(max) { if (max <= 40) return Math.max(4, Math.ceil(max / 4) * 4); var p = Math.pow(10, Math.floor(Math.log(max) / Math.LN10)), n = Math.ceil(max / p * 2) / 2 * p; return Math.ceil(n / 4) * 4; }

  function line(host, labels, values, o) {
    o = o || {}; var has = values.some(function (v) { return v != null; });
    if (!has) { msg(host, o.empty || 'No data recorded for this period.'); return; }
    clear(host); var W = 360, H = 214, L = 38, R = 14, T = 26, B = 44, max = o.max || 100, w = W - L - R, h = H - T - B;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label || 'Line chart', 'class': 'shc-svg' });
    for (var i = 0; i <= 4; i++) { var y = T + h * i / 4; svg.appendChild(el('line', { x1: L, x2: W - R, y1: y, y2: y, 'class': 'shc-grid' }));
      svg.appendChild(el('text', { x: L - 5, y: y + 3, 'text-anchor': 'end', 'class': 'shc-ax' }, Math.round(max - max * i / 4) + (o.suffix || ''))); }
    var n = labels.length, step = n > 1 ? w / (n - 1) : 0, px = function (i) { return n > 1 ? L + i * step : L + w / 2; }, py = function (v) { return T + h * (1 - Math.min(Math.max(v, 0), max) / max); };
    if (o.second && o.second.values) { var sg = [], flush2 = function () { if (sg.length > 1) svg.appendChild(el('polyline', { points: sg.join(' '), fill: 'none', stroke: o.second.color || '#94a3b8', 'stroke-width': 2, 'stroke-dasharray': '5 4', 'stroke-linejoin': 'round' })); sg = []; };
      o.second.values.forEach(function (v, i) { if (v == null) { flush2(); } else { sg.push((n > 1 ? L + i * (w / (n - 1)) : L + w / 2).toFixed(1) + ',' + (T + h * (1 - Math.min(Math.max(v, 0), max) / max)).toFixed(1)); } }); flush2(); }
    var col = o.color || '#1a6fe8', seg = [];
    function flush() { if (seg.length > 1) svg.appendChild(el('polyline', { points: seg.join(' '), fill: 'none', stroke: col, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' })); seg = []; }
    values.forEach(function (v, i) { if (v == null) { flush(); } else { seg.push(px(i).toFixed(1) + ',' + py(v).toFixed(1)); } }); flush();
    var every = n > 8 ? 2 : 1;
    values.forEach(function (v, i) {
      if (v != null) { var c = el('circle', { cx: px(i), cy: py(v), r: 4, fill: col, stroke: '#fff', 'stroke-width': 1.5 }); c.appendChild(el('title', {}, labels[i] + ': ' + v + (o.suffix || ''))); svg.appendChild(c);
        if (n <= 8) svg.appendChild(el('text', { x: px(i), y: py(v) - 8, 'text-anchor': 'middle', 'class': 'shc-val' }, Math.round(v))); }
      if (i % every === 0) labelLines(svg, px(i), H - B + 14, labels[i], 'shc-ax');
    });
    host.appendChild(svg);
  }

  function bars(host, labels, values, o) {
    o = o || {}; if (!values.length || !values.some(function (v) { return v != null && v > 0; })) { msg(host, o.empty || 'No data recorded yet.'); return; }
    clear(host); var W = 360, H = 214, L = 38, R = 10, T = 26, B = 48, max = o.fixedMax || nice(Math.max.apply(null, values.map(function (v) { return v == null ? 0 : v; }))), w = W - L - R, h = H - T - B, n = values.length;
    var slot = w / n, bw = Math.min(40, slot * 0.62), pal = o.colors || ['#1a6fe8', '#3b82f6', '#2563eb', '#1d4ed8', '#0a2a6b'];
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label || 'Bar chart', 'class': 'shc-svg' });
    for (var i = 0; i <= 4; i++) { var y = T + h * i / 4; svg.appendChild(el('line', { x1: L, x2: W - R, y1: y, y2: y, 'class': 'shc-grid' })); svg.appendChild(el('text', { x: L - 5, y: y + 3, 'text-anchor': 'end', 'class': 'shc-ax' }, Math.round(max - max * i / 4))); }
    values.forEach(function (v, i) { if (v == null) { labelLines(svg, L + slot * i + slot / 2, H - B + 14, labels[i] + ' (—)', 'shc-ax'); return; } var bh = h * v / max, x = L + slot * i + (slot - bw) / 2, y = T + h - bh;
      var r = el('rect', { x: x, y: y, width: bw, height: bh, rx: 3, fill: pal[i % pal.length] }); r.appendChild(el('title', {}, labels[i] + ': ' + v)); svg.appendChild(r);
      svg.appendChild(el('text', { x: x + bw / 2, y: y - 4, 'text-anchor': 'middle', 'class': 'shc-val' }, v));
      labelLines(svg, x + bw / 2, H - B + 14, labels[i], 'shc-ax'); });
    host.appendChild(svg);
  }
  window.ShCharts = { line: line, bars: bars };

  /* ---- generic: any <div data-sh-line='{"labels":[..],"values":[..],"max":100,"suffix":"%"}'> ---- */
  document.querySelectorAll('[data-sh-line]').forEach(function (h) { try { var d = JSON.parse(h.getAttribute('data-sh-line')); line(h, d.labels, d.values, { max: d.max, suffix: d.suffix, color: d.color, label: d.label, empty: d.empty, second: d.second }); } catch (e) {} });

  document.querySelectorAll('[data-sh-bars]').forEach(function (h) { try { var d = JSON.parse(h.getAttribute('data-sh-bars')); bars(h, d.labels, d.values, { label: d.label, empty: d.empty, colors: d.scoreColors ? d.values.map(function (v) { return v == null ? '#cbd5e1' : v >= 70 ? '#27c25a' : v >= 50 ? '#1a6fe8' : '#ffae1a'; }) : d.colors, fixedMax: d.max }); } catch (e) {} });

  /* ---- admin dashboard ---- */
  var src = document.getElementById('adChartsData'); if (!src) return; var D; try { D = JSON.parse(src.textContent); } catch (e) { return; }
  var st = { group: 'students', range: 'this_week', mode: 'term' };
  function press(sel, attr, val) { document.querySelectorAll(sel).forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute(attr) === val ? 'true' : 'false'); }); }
  function drawAtt() {
    var host = document.getElementById('attChart'); if (!host) return; var d = D.attendance[st.group][st.range];
    var who = st.group === 'students' ? 'Student' : 'Staff'; var note = document.getElementById('attNote'); if (note) note.textContent = who + ' attendance · ' + d.note;
    line(host, d.labels, d.values, { max: 100, suffix: '%', color: st.group === 'students' ? '#1a6fe8' : '#8b5cf6', label: who + ' attendance, ' + d.note, empty: 'No ' + who.toLowerCase() + ' attendance recorded for this period.' });
    press('[data-att-group]', 'data-att-group', st.group); press('[data-att-range]', 'data-att-range', st.range);
  }
  function drawEnrol() { var host = document.getElementById('enrolChart'); if (!host) return; var d = D.enrol[st.mode];
    bars(host, d.labels, d.values, { label: 'Enrolment by ' + st.mode, empty: 'No enrolment recorded yet.' }); press('[data-enrol-mode]', 'data-enrol-mode', st.mode); }
  function drawLevels() { var host = document.getElementById('levelChart'); if (!host) return;
    bars(host, D.levels.map(function (l) { return l.label; }), D.levels.map(function (l) { return l.count; }), { label: 'Enrolment by class level', colors: ['#7c3aed', '#8b5cf6', '#6d28d9', '#a78bfa'], empty: 'No students enrolled yet.' }); }
  document.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('button'); if (!b) return;
    if (b.hasAttribute('data-att-group')) { st.group = b.getAttribute('data-att-group'); drawAtt(); }
    else if (b.hasAttribute('data-att-range')) { st.range = b.getAttribute('data-att-range'); drawAtt(); }
    else if (b.hasAttribute('data-enrol-mode')) { st.mode = b.getAttribute('data-enrol-mode'); drawEnrol(); } });
  drawAtt(); drawEnrol(); drawLevels();
})();
