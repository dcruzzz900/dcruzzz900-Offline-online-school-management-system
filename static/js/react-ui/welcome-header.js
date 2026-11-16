/* V107: DashboardWelcomeHeader - ONE reusable React component for every dashboard's welcome banner.
   Props (from the server, per signed-in person): heading, description, tz (the school's IANA timezone), utc_ms (server clock anchor).
   It shows the day, date and 12-hour time in the SCHOOL's timezone and ticks every second without a page refresh. The clock is anchored
   to the server's time (not the device's possibly-wrong clock) and re-synced as the page stays open. Light/dark are handled by CSS. */
(function () {
  "use strict";
  var hosts = document.querySelectorAll("[data-welcome-header]");
  if (!hosts.length) return;
  var CDN = ["https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js", "https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"];
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.crossOrigin = "anonymous"; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  var ready = (window.React && window.ReactDOM) ? Promise.resolve() : load(CDN[0]).then(function () { return load(CDN[1]); });

  function format(ms, tz) {
    var d = new Date(ms), parts = {};
    try {
      new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true })
        .formatToParts(d).forEach(function (p) { parts[p.type] = p.value; });
    } catch (e) { return null; }
    return { date: parts.weekday + ", " + parts.day + " " + parts.month + " " + parts.year, time: parts.hour + ":" + parts.minute + " " + String(parts.dayPeriod || "").toUpperCase() };
  }

  ready.then(function () {
    var React = window.React, h = React.createElement, ico = function (html) { return h("span", { dangerouslySetInnerHTML: { __html: html } }); };
    function DashboardWelcomeHeader(p) {
      var offset = React.useRef(p.utc_ms - Date.now());                      // server time - device time
      var s0 = React.useState(function () { return format(Date.now() + offset.current, p.tz) || { date: p.date, time: p.time }; }), now = s0[0], setNow = s0[1];
      React.useEffect(function () {
        var tick = function () { var f = format(Date.now() + offset.current, p.tz); if (f) setNow(f); };
        var t = setInterval(tick, 1000); document.addEventListener("visibilitychange", tick);
        return function () { clearInterval(t); document.removeEventListener("visibilitychange", tick); };
      }, []);
      return h("section", { className: "wh-banner", style: p.style, "aria-label": "Welcome" },
        h("div", { className: "wh-banner-main" }, ico(p.logo), h("div", null, h("h1", null, p.heading), h("p", null, p.description))),
        h("div", { className: "wh-banner-clock", role: "timer", "aria-live": "off" },
          h("div", null, ico(p.calIcon), h("span", { "data-clock-date": true }, now.date)),
          h("div", null, ico(p.clockIcon), h("span", { "data-clock-time": true }, now.time))));
    }
    window.DashboardWelcomeHeader = DashboardWelcomeHeader;
    hosts.forEach(function (el) {
      var cfg = {}; try { cfg = JSON.parse(el.getAttribute("data-config")); } catch (e) { return; }
      var icons = el.querySelectorAll(".wh-banner-logo, .wh-banner-clock svg");
      var logo = (el.querySelector(".wh-banner-logo") || {}).innerHTML || "";
      var svgs = el.querySelectorAll(".wh-banner-clock > div > svg");
      var wrap = document.createElement("div"); wrap.style.display = "contents"; el.parentNode.replaceChild(wrap, el);
      var logoHtml = '<span class="wh-banner-logo">' + logo + "</span>";
      ReactDOM.createRoot(wrap).render(h(DashboardWelcomeHeader, Object.assign({}, cfg, {
        style: { "--banner-img": getComputedStyle(el).getPropertyValue("--banner-img") || el.style.getPropertyValue("--banner-img") },
        logo: logo, calIcon: svgs[0] ? svgs[0].outerHTML : "", clockIcon: svgs[1] ? svgs[1].outerHTML : "" })));
    });
  }).catch(function () { /* CDN blocked: the server-rendered header stays (without the live tick) */ });
})();
