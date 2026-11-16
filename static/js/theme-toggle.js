/* V106: light / dark mode. The early <head> script in base.html applies the stored choice before first paint (no flash);
   this file wires every [data-theme-toggle] button, persists the choice, keeps <meta name="theme-color"> in sync and tells
   charts to restyle through a "sh-theme-change" event. With no stored choice the OS preference is followed. */
(function () {
  var KEY = 'sh-theme', root = document.documentElement;
  function stored() { try { var t = localStorage.getItem(KEY); return t === 'dark' || t === 'light' ? t : null; } catch (e) { return null; } }
  function current() { return root.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light'; }
  var SCALES = [90, 100, 115, 130, 150], body = document.body;
  var signedIn = body && body.getAttribute('data-actor') === '1', prefsUrl = body && body.getAttribute('data-prefs-url');
  /* V107: the choice is kept per person on the server (follows them across devices) and mirrored on the device (works signed-out) */
  function csrf() { var m = document.querySelector('input[name="csrf_token"]'); return m ? m.value : (window.__csrf || ''); }
  var saveTimer = null;
  function savePrefs(patch) {
    if (!signedIn || !prefsUrl) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      var cur = { theme: current(), font_scale: scale() };
      fetch(prefsUrl, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': (document.body.getAttribute('data-csrf') || csrf()) },
        body: JSON.stringify(Object.assign(cur, patch)) }).catch(function () {});
    }, 350);
  }
  function scale() { var v = parseInt(root.getAttribute('data-font-scale'), 10); return SCALES.indexOf(v) > -1 ? v : 100; }
  function paintScale(v, persist) {
    root.setAttribute('data-font-scale', v);
    if (persist) { try { localStorage.setItem('sh-font', v); } catch (e) {} savePrefs({ font_scale: v }); }
    document.querySelectorAll('[data-fs-label]').forEach(function (n) { n.textContent = v + '%'; });
    document.querySelectorAll('[data-fs-step="-1"]').forEach(function (b) { b.disabled = v <= SCALES[0]; });
    document.querySelectorAll('[data-fs-step="1"]').forEach(function (b) { b.disabled = v >= SCALES[SCALES.length - 1]; });
    try { window.dispatchEvent(new CustomEvent('sh-font-change', { detail: { scale: v } })); } catch (e) {}
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-fs-step]'); if (!b) return;
    e.preventDefault(); var st = parseInt(b.getAttribute('data-fs-step'), 10), i = SCALES.indexOf(scale());
    paintScale(st === 0 ? 100 : SCALES[Math.max(0, Math.min(SCALES.length - 1, i + st))], true);
  });
  function paint(theme, persist) {
    root.setAttribute('data-bs-theme', theme);
    if (persist) { try { localStorage.setItem(KEY, theme); } catch (e) {} savePrefs({ theme: theme }); }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      if (!meta.dataset.light) meta.dataset.light = meta.getAttribute('content') || '';
      meta.setAttribute('content', theme === 'dark' ? '#0f172a' : meta.dataset.light);
    }
    document.querySelectorAll('[data-theme-toggle]').forEach(function (b) {
      var dark = theme === 'dark';
      b.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      b.setAttribute('aria-pressed', dark ? 'true' : 'false');
      var l = b.querySelector('.tt-label'); if (l) l.textContent = dark ? 'Light mode' : 'Dark mode';
    });
    try { window.dispatchEvent(new CustomEvent('sh-theme-change', { detail: { theme: theme } })); } catch (e) {}
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-theme-toggle]');
    if (!b) return;
    e.preventDefault(); paint(current() === 'dark' ? 'light' : 'dark', true);
  });
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var follow = function (ev) { if (!stored()) paint(ev.matches ? 'dark' : 'light', false); };
    if (mq.addEventListener) mq.addEventListener('change', follow); else if (mq.addListener) mq.addListener(follow);
  }
  window.addEventListener('storage', function (e) { if (e.key === KEY && (e.newValue === 'dark' || e.newValue === 'light')) paint(e.newValue, false); });
  paint(current(), false); paintScale(scale(), false);
  window.SchoolHubTheme = { get: current, set: function (t) { paint(t === 'dark' ? 'dark' : 'light', true); } };
})();
