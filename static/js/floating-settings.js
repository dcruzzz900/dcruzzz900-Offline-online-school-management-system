/* V112: draggable floating "Display settings" control.
   - Drag the round button anywhere (mouse, touch or pen); a tap/click without movement opens the panel.
   - Keyboard: Enter/Space opens; Shift+Arrow keys nudge it (10px); Escape closes.
   - Its position is saved on this device as screen fractions (so it stays sensible on rotation / resize) and always clamped on-screen.
   - Text size and light/dark are handled by theme-toggle.js (saved per person on the server and per device). */
(function () {
  var fab = document.getElementById('shFab'); if (!fab) return;
  var btn = document.getElementById('shFabBtn'), panel = document.getElementById('shFabPanel');
  var KEY = 'sh-fab-pos', SIZE = 48, M = 8, DRAG_PX = 6;
  var root = document.documentElement, pos = null, dragging = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0, pid = null;

  function vw() { return root.clientWidth || window.innerWidth; }
  function vh() { return window.innerHeight; }
  function reserveBottom() { /* keep clear of the phone bottom tab bar when it is showing */
    var t = document.querySelector('.mobile-tabs'); return (t && t.offsetParent !== null) ? t.offsetHeight + 16 : 0;
  }
  function bounds() { return { minX: M, maxX: Math.max(M, vw() - SIZE - M), minY: M, maxY: Math.max(M, vh() - SIZE - M - reserveBottom()) }; }
  function clamp(p) { var b = bounds(); return { x: Math.min(b.maxX, Math.max(b.minX, p.x)), y: Math.min(b.maxY, Math.max(b.minY, p.y)) }; }
  function read() { try { var s = JSON.parse(localStorage.getItem(KEY)); if (s && typeof s.fx === 'number' && typeof s.fy === 'number') return s; } catch (e) {} return null; }
  function write() { try { var b = bounds(); localStorage.setItem(KEY, JSON.stringify({ fx: b.maxX > b.minX ? (pos.x - b.minX) / (b.maxX - b.minX) : 1, fy: b.maxY > b.minY ? (pos.y - b.minY) / (b.maxY - b.minY) : 1 })); } catch (e) {} }
  function fromSaved() { var s = read(), b = bounds(); return s ? { x: b.minX + s.fx * (b.maxX - b.minX), y: b.minY + s.fy * (b.maxY - b.minY) } : { x: b.maxX, y: b.maxY - 56 }; }
  function apply() {
    pos = clamp(pos); fab.style.left = pos.x + 'px'; fab.style.top = pos.y + 'px'; fab.style.right = 'auto'; fab.style.bottom = 'auto';
    fab.classList.toggle('sh-right', pos.x + SIZE / 2 > vw() / 2); fab.classList.toggle('sh-low', pos.y + SIZE / 2 > vh() / 2);
  }
  function open(o) {
    panel.hidden = !o; btn.setAttribute('aria-expanded', o ? 'true' : 'false'); fab.classList.toggle('sh-open', o);
  }

  btn.addEventListener('pointerdown', function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    dragging = true; moved = false; pid = e.pointerId; sx = e.clientX; sy = e.clientY; ox = pos.x; oy = pos.y;
    try { btn.setPointerCapture(pid); } catch (x) {}
  });
  btn.addEventListener('pointermove', function (e) {
    if (!dragging || e.pointerId !== pid) return;
    var dx = e.clientX - sx, dy = e.clientY - sy;
    if (!moved && Math.abs(dx) + Math.abs(dy) < DRAG_PX) return;
    if (!moved) { moved = true; open(false); fab.classList.add('sh-dragging'); }
    pos = { x: ox + dx, y: oy + dy }; apply();
  });
  function end(e) {
    if (!dragging || (e && e.pointerId !== pid)) return;
    dragging = false; fab.classList.remove('sh-dragging'); try { btn.releasePointerCapture(pid); } catch (x) {}
    if (moved) { write(); } else { open(panel.hidden); }
  }
  btn.addEventListener('pointerup', end); btn.addEventListener('pointercancel', end);
  btn.addEventListener('click', function (e) { e.preventDefault(); }); /* pointerup already handled tap; keyboard handled below */
  btn.addEventListener('keydown', function (e) {
    var step = 10, d = null;
    if ((e.key === 'Enter' || e.key === ' ') && !e.shiftKey) { e.preventDefault(); open(panel.hidden); return; }
    if (e.shiftKey) { d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key]; }
    if (d) { e.preventDefault(); pos = { x: pos.x + d[0], y: pos.y + d[1] }; apply(); write(); }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) { open(false); btn.focus(); } });
  document.addEventListener('pointerdown', function (e) { if (!panel.hidden && !fab.contains(e.target)) open(false); });
  fab.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('[data-fab-reset]')) { try { localStorage.removeItem(KEY); } catch (x) {} pos = fromSaved(); apply(); }
  });
  var rt = null; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { pos = fromSaved(); apply(); }, 80); });
  window.addEventListener('orientationchange', function () { setTimeout(function () { pos = fromSaved(); apply(); }, 200); });
  pos = fromSaved(); apply(); fab.classList.add('sh-ready');
})();
