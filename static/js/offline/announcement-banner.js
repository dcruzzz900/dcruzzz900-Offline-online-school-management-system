/* V107: auto-hide for announcement banners whose administrator set "display for N seconds". The countdown pauses while the banner is hovered
   or focused (so it can be read / dismissed), and never applies to Urgent banners with no timer. The banner returns on the next page load
   until it expires or the person dismisses it with the x button. */
(function () {
  "use strict";
  document.querySelectorAll(".ann[data-ann-seconds]").forEach(function (el) {
    var s = parseInt(el.getAttribute("data-ann-seconds"), 10); if (!(s > 0)) return;
    var left = s * 1000, last = Date.now(), paused = false;
    el.addEventListener("mouseenter", function () { paused = true; }); el.addEventListener("mouseleave", function () { paused = false; last = Date.now(); });
    el.addEventListener("focusin", function () { paused = true; }); el.addEventListener("focusout", function () { paused = false; last = Date.now(); });
    var t = setInterval(function () {
      var now = Date.now(); if (!paused) left -= now - last; last = now;
      if (left <= 0) { clearInterval(t); el.classList.add("ann-hiding"); setTimeout(function () { el.hidden = true; }, 400); }
    }, 250);
  });
})();
