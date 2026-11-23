/* V112: "Add ..." forms start collapsed; the page's + Add button expands them (and a Close button collapses them again).
   <button data-toggle-form="#id" aria-expanded="false" aria-controls="id"> controls <section id="id" hidden>. Opening scrolls to the form and focuses its first field.
   A link or URL ending in #id (e.g. /admin/students#add-student) opens it automatically. */
(function () {
  function btns(id) { return document.querySelectorAll('[data-toggle-form="#' + id + '"]'); }
  function setOpen(box, open, focus) {
    box.hidden = !open; btns(box.id).forEach(function (b) { b.setAttribute('aria-expanded', open ? 'true' : 'false'); });
    if (open) { box.classList.add('form-expanding'); if (focus !== false) { box.scrollIntoView({ behavior: 'smooth', block: 'start' }); var f = box.querySelector('input:not([type=hidden]),select,textarea'); if (f) setTimeout(function () { try { f.focus({ preventScroll: true }); } catch (e) { f.focus(); } }, 250); } }
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-toggle-form]'); if (!b) return;
    var box = document.querySelector(b.getAttribute('data-toggle-form')); if (!box) return; e.preventDefault(); setOpen(box, box.hidden);
  });
  function fromHash() { var id = (location.hash || '').slice(1); var box = id && document.getElementById(id); if (box && box.hasAttribute('data-collapsible')) setOpen(box, true); }
  window.addEventListener('hashchange', fromHash); fromHash();
})();
