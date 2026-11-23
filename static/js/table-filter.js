/* V112: tiny client-side filter for v106 list pages. <input data-filter-table="#id"> filters rows by text; <select data-filter-table="#id" data-filter-attr="level"> by a data-* attribute. */
(function () {
  function rows(sel) { var t = document.querySelector(sel); return t ? Array.prototype.slice.call(t.querySelectorAll('tbody tr')) : []; }
  function apply(tableSel) {
    var q = '', attrs = {};
    document.querySelectorAll('[data-filter-table="' + tableSel + '"]').forEach(function (c) {
      if (c.tagName === 'SELECT') { if (c.value) attrs[c.getAttribute('data-filter-attr')] = c.value; } else { q = c.value.trim().toLowerCase(); }
    });
    var shown = 0;
    rows(tableSel).forEach(function (r) {
      if (r.hasAttribute('data-empty-row')) return;
      var ok = (!q || r.textContent.toLowerCase().indexOf(q) > -1) && Object.keys(attrs).every(function (k) { return (r.getAttribute('data-' + k) || '') === attrs[k]; });
      r.hidden = !ok; if (ok) shown++;
    });
    var n = document.querySelector('[data-filter-count="' + tableSel + '"]'); if (n) n.textContent = shown;
  }
  document.addEventListener('input', function (e) { var s = e.target.getAttribute && e.target.getAttribute('data-filter-table'); if (s) apply(s); });
  document.addEventListener('change', function (e) { var s = e.target.getAttribute && e.target.getAttribute('data-filter-table'); if (s) apply(s); });
})();
