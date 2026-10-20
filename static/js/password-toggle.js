/* Show/hide control for every password field. Passwords stay hidden by default; toggling only flips the input type, so
   whatever was typed is kept. Works with touch, keyboard (Tab + Enter/Space) and screen readers (aria-pressed + live label). */
(function () {
  var EYE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="2" d="M1.5 12S5.5 5 12 5s10.5 7 10.5 7-4 7-10.5 7S1.5 12 1.5 12z"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
  var EYE_OFF = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="2" d="M3 3l18 18M10.6 5.2A9.9 9.9 0 0112 5c6.5 0 10.5 7 10.5 7a17 17 0 01-3.2 3.9M6.4 6.5C3.4 8.4 1.5 12 1.5 12S5.5 19 12 19c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 004.2 4.2"/></svg>';
  function enhance(input) {
    if (input.dataset.pwToggle || input.hasAttribute('data-no-toggle')) return;
    input.dataset.pwToggle = '1';
    var wrap = document.createElement('span');
    wrap.className = 'pw-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-toggle';
    btn.setAttribute('aria-pressed', 'false');
    btn.setAttribute('aria-label', 'Show password');
    btn.innerHTML = EYE;
    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.innerHTML = show ? EYE_OFF : EYE;
      input.focus({ preventScroll: true });
    });
    wrap.appendChild(btn);
    // never leave a password visible when the form is sent or the tab is restored
    if (input.form) input.form.addEventListener('submit', function () { if (input.type !== 'password') { input.type = 'password'; } });
  }
  function scan(root) { (root || document).querySelectorAll('input[type="password"]').forEach(enhance); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { scan(); }); else scan();
  if (window.MutationObserver) new MutationObserver(function (m) { m.forEach(function (r) { r.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); }); }); }).observe(document.documentElement, { childList: true, subtree: true });
})();
