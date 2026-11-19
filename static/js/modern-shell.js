(function () {
  function qs(s, r) { return (r || document).querySelector(s); }

  // The sidebar is the same off-canvas overlay drawer at every breakpoint
  // (desktop/tablet behave exactly like phone used to) — one set of
  // open/close mechanics, no breakpoint branching needed here. The icon's
  // colors adapt automatically via CSS depending on the topbar underneath.

  function ensureBackdrop() {
    var b = qs('.sidebar-backdrop');
    if (!b) {
      b = document.createElement('div');
      b.className = 'sidebar-backdrop';
      document.body.appendChild(b);
    }
    return b;
  }

  function setToggleState(btn, expanded) {
    if (!btn) return;
    btn.classList.toggle('open', expanded);
    btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    btn.setAttribute('aria-label', expanded ? 'Close menu' : 'Open menu');
  }

  function closeSidebar() {
    var side = qs('.sidebar');
    var back = qs('.sidebar-backdrop');
    if (side) side.classList.remove('open');
    setToggleState(qs('.hamburger'), false);
    if (back) back.classList.remove('show');
    document.body.style.overflow = '';
  }

  function openSidebar() {
    var side = qs('.sidebar');
    var back = ensureBackdrop();
    if (side) side.classList.add('open');
    setToggleState(qs('.hamburger'), true);
    back.classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function toggleSidebar() {
    var side = qs('.sidebar');
    if (side && side.classList.contains('open')) closeSidebar();
    else openSidebar();
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('.hamburger');
    if (btn) { e.preventDefault(); toggleSidebar(); return; }
    if (e.target.classList && e.target.classList.contains('sidebar-backdrop')) closeSidebar();
    if (e.target.closest && e.target.closest('.sidebar .nav-item')) closeSidebar();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSidebar();
  });
})();

// ---- v111 integration additions -------------------------------------------
(function () {
  function qs(s, r) { return (r || document).querySelector(s); }
  // Mobile "More" tab opens the same drawer so every role link stays reachable.
  document.addEventListener('click', function (e) {
    var more = e.target.closest && e.target.closest('#tabsMore');
    if (more) { e.preventDefault(); var h = qs('.hamburger'); if (h) h.click(); }
  });
  // Mark the current page in the sidebar (aria-current + .active), longest href match wins.
  var path = location.pathname.replace(/\/+$/, '') || '/';
  var best = null, bestLen = -1;
  document.querySelectorAll('.sidebar nav a.nav-item').forEach(function (a) {
    var h = (a.getAttribute('href') || '').split('?')[0].split('#')[0].replace(/\/+$/, '') || '/';
    if (h === '#' ) return;
    if (path === h || (h.length > 1 && path.indexOf(h + '/') === 0)) {
      if (h.length > bestLen) { best = a; bestLen = h.length; }
    }
  });
  if (best) { best.classList.add('active'); best.setAttribute('aria-current', 'page'); }
  // Keep the active item visible when the drawer opens on a long menu.
  var h = qs('.hamburger');
  if (h) h.addEventListener('click', function () { setTimeout(function () { if (best && best.scrollIntoView) best.scrollIntoView({block: 'nearest'}); }, 280); });
})();
