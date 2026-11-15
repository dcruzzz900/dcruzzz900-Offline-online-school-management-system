/* V106: light/dark mode toggle. The actual theme is already set on <html data-theme="..">
   before paint by the inline script in base.html's <head> (avoids a flash of the wrong theme);
   this file only wires up the button click + keeps it in sync with whichever page it's on. */
(function () {
  "use strict";

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("shub-theme", theme); } catch (e) {}
    var btn = document.getElementById("themeToggleBtn");
    if (btn) {
      var dark = theme === "dark";
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("themeToggleBtn");
    if (!btn) return;
    // Reflect whatever the no-flash head script already decided.
    apply(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      apply(current === "dark" ? "light" : "dark");
    });
  });
})();
