/* V106: light / dark mode. The early <head> script in base.html applies the stored choice before first paint (no flash);
   this file wires every [data-theme-toggle] button, persists the choice, keeps <meta name="theme-color"> in sync and tells
   charts to restyle through a "sh-theme-change" event. With no stored choice the OS preference is followed. */
(function () {
  var KEY = 'sh-theme', root = document.documentElement;
  function stored() { try { var t = localStorage.getItem(KEY); return t === 'dark' || t === 'light' ? t : null; } catch (e) { return null; } }
  function current() { return root.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light'; }
  function paint(theme, persist) {
    root.setAttribute('data-bs-theme', theme);
    if (persist) { try { localStorage.setItem(KEY, theme); } catch (e) {} }
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
  paint(current(), false);
  window.SchoolHubTheme = { get: current, set: function (t) { paint(t === 'dark' ? 'dark' : 'light', true); } };
})();
