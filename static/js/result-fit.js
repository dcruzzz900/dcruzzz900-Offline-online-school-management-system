/* V100: on-screen "fit to screen" for the Cumulative / Annual Performance table.
   On a phone (<=820px) the table is laid out at its real A4-portrait width (the same layout Print/PDF use,
   so every column incl. Remark is present) and then scaled down to the screen width with a transform --
   nothing is hidden behind a scroll box and nothing is cut off. On wider screens it simply fills the sheet.
   Screen only: Print/PDF never match the media query, so they keep the normal full-width layout. */
(function () {
  function fit() {
    var small = window.matchMedia && window.matchMedia('screen and (max-width:820px)').matches;
    var wraps = document.querySelectorAll('.rs-cum-scroll');
    for (var i = 0; i < wraps.length; i++) {
      var w = wraps[i], t = w.querySelector('.rs-cum-table');
      if (!t) continue;
      t.style.transform = ''; t.style.transformOrigin = ''; t.style.width = ''; t.style.maxWidth = ''; w.style.height = '';
      if (!small) continue;
      var real = 190 * 96 / 25.4;                       // 190mm: the table width on an A4 portrait sheet
      var avail = w.clientWidth - 3;
      if (avail <= 0 || avail >= real) continue;
      var k = avail / real;
      t.style.width = real + 'px'; t.style.maxWidth = 'none';
      t.style.transformOrigin = '0 0'; t.style.transform = 'scale(' + k.toFixed(4) + ')';
      w.style.height = Math.ceil(t.offsetHeight * k + 3) + 'px';
    }
  }
  window.addEventListener('load', fit);
  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', fit);
  if (document.readyState !== 'loading') fit(); else document.addEventListener('DOMContentLoaded', fit);
})();
