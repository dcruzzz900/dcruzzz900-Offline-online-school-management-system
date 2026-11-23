/* V112: sliding announcement strip. One slide visible at a time; auto-advances every 6s with a sliding transition when there are several;
   pauses while hovered/focused; dots + swipe to move manually. Works alongside announcement-banner.js (auto-hide timers use .ann[data-ann-seconds]). */
(function () {
  "use strict";
  var wrap = document.querySelector('[data-announcement-banners]'); if (!wrap) return;
  var track = wrap.querySelector('.ann-track'), dots = wrap.querySelectorAll('[data-ann-go]'), i = 0, timer = null, paused = false;
  function n() { return track.children.length; }
  function go(k) {
    if (!n()) return; i = (k + n()) % n(); track.style.transform = 'translateX(' + (-100 * i) + '%)';
    dots.forEach(function (d, j) { d.setAttribute('aria-current', j === i ? 'true' : 'false'); });
  }
  function start() { stop(); if (n() > 1 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) timer = setInterval(function () { if (!paused) go(i + 1); }, 6000); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  dots.forEach(function (d) { d.addEventListener('click', function () { go(parseInt(d.getAttribute('data-ann-go'), 10)); start(); }); });
  wrap.addEventListener('mouseenter', function () { paused = true; }); wrap.addEventListener('mouseleave', function () { paused = false; });
  wrap.addEventListener('focusin', function () { paused = true; }); wrap.addEventListener('focusout', function () { paused = false; });
  var x0 = null; wrap.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; paused = true; }, { passive: true });
  wrap.addEventListener('touchend', function (e) { if (x0 != null) { var dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) { go(i + (dx < 0 ? 1 : -1)); start(); } } x0 = null; paused = false; }, { passive: true });
  /* when a slide is auto-hidden or dismissed the track shrinks: keep the index valid */
  new MutationObserver(function () { if (!n()) { wrap.remove(); stop(); } else { go(Math.min(i, n() - 1)); } }).observe(track, { childList: true });
  go(0); start();
})();
