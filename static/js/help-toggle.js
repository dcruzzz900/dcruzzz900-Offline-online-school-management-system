/* Help text is hidden until asked for: <button class="help-btn" data-help="ID">?</button> toggles the element with that id.
   Hidden help takes no space. Works with touch, keyboard and screen readers (aria-expanded / aria-controls). */
(function () {
  function wire(btn) {
    if (btn.dataset.wired) return; btn.dataset.wired = "1";
    var target = document.getElementById(btn.getAttribute("data-help"));
    if (!target) return;
    btn.setAttribute("aria-controls", target.id); btn.setAttribute("aria-expanded", "false");
    if (!btn.getAttribute("aria-label")) btn.setAttribute("aria-label", "Show help");
    target.hidden = true;
    btn.addEventListener("click", function () {
      var open = target.hidden; target.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Hide help" : "Show help");
    });
  }
  function scan(root) { (root || document).querySelectorAll(".help-btn[data-help]").forEach(wire); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { scan(); }); else scan();
})();
