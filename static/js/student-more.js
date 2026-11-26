/* V115: Student mobile bottom menu - the "More" tab opens a small sheet above the tab bar (AI Tutor, Timetable, Profile, Account, Logout).
   Closes on: tapping outside, Escape, choosing a link, or tapping More again. Pure JS, no dependencies, works offline. */
(function () {
  "use strict";
  var btn = document.getElementById('studentMore'), sheet = document.getElementById('studentMoreSheet');
  if (!btn || !sheet) return;
  function setOpen(open) {
    sheet.hidden = !open; btn.setAttribute('aria-expanded', open ? 'true' : 'false'); btn.classList.toggle('open', open);
    if (open) { var a = sheet.querySelector('a'); if (a) { try { a.focus({ preventScroll: true }); } catch (e) { a.focus(); } } }
  }
  btn.addEventListener('click', function (e) { e.preventDefault(); setOpen(sheet.hidden); });
  document.addEventListener('click', function (e) {
    if (sheet.hidden) return;
    if (e.target.closest && (e.target.closest('#studentMoreSheet') || e.target.closest('#studentMore'))) { if (e.target.closest('#studentMoreSheet a')) setOpen(false); return; }
    setOpen(false);
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !sheet.hidden) { setOpen(false); btn.focus(); } });
  /* the bar only exists on phones: if the window grows past the phone breakpoint, close the sheet */
  window.addEventListener('resize', function () { if (window.innerWidth > 700 && !sheet.hidden) setOpen(false); });
})();
