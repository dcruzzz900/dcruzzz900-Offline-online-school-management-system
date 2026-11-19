/* V107: attractive passport preview before saving. Enhances every photograph upload (input[type=file][name=photo]):
   checks type and size in the browser, then shows the picture in the SAME 4:5 frame the server will store - using the same rule
   (close to 4:5: fill and trim a little from the bottom; any other shape: show the whole photograph on a soft backdrop), so the
   preview matches what is saved. The server (passport_fit.py) re-checks and normalises regardless. React is loaded only when needed. */
(function () {
  "use strict";
  var inputs = document.querySelectorAll('input[type="file"][name="photo"]');
  if (!inputs.length) return;
  var CDN = ["https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js", "https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"];
  var OK = /^image\/(png|jpe?g|gif)$/, TOL = 0.18, TARGET = 4 / 5;
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.crossOrigin = "anonymous"; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  var ready = (window.React && window.ReactDOM) ? Promise.resolve() : load(CDN[0]).then(function () { return load(CDN[1]); });
  ready.then(function () {
    var React = window.React, h = React.createElement;
    function Preview(p) {
      var s0 = React.useState(null), info = s0[0], setInfo = s0[1];
      React.useEffect(function () {
        var input = p.input;
        var on = function () {
          var f = input.files && input.files[0];
          if (!f) { setInfo(null); return; }
          var max = parseInt(input.getAttribute("data-max-bytes"), 10) || 512000;
          if (!OK.test(f.type)) { setInfo({ error: "Choose a PNG, JPG or GIF photograph." }); return; }
          if (f.size > max) { setInfo({ error: "This photograph is " + Math.round(f.size / 1024) + " KB - the limit is " + Math.round(max / 1024) + " KB." }); return; }
          var url = URL.createObjectURL(f), img = new Image();
          img.onload = function () { setInfo({ url: url, w: img.naturalWidth, h: img.naturalHeight, name: f.name, kb: Math.round(f.size / 1024) }); };
          img.onerror = function () { setInfo({ error: "That file could not be read as a picture." }); };
          img.src = url;
        };
        input.addEventListener("change", on); return function () { input.removeEventListener("change", on); };
      }, []);
      if (!info) return null;
      if (info.error) return h("div", { className: "alert alert-danger py-2 mt-2", role: "alert" }, info.error);
      var near = Math.abs(info.w / info.h - TARGET) / TARGET <= TOL;
      return h("div", { className: "passport-preview d-flex gap-3 align-items-center mt-2" },
        h("div", { className: "passport-frame", style: { backgroundImage: near ? "none" : "url(" + info.url + ")" } },
          h("img", { src: info.url, alt: "Passport preview", className: near ? "pp-fill" : "pp-fit" })),
        h("div", { className: "small" }, h("div", { className: "fw-semibold" }, "Preview"), h("div", { className: "muted" }, info.name + " · " + info.kb + " KB · " + info.w + "×" + info.h),
          h("div", { className: "muted" }, near ? "Fits the passport frame." : "Shown whole, without cropping, on a soft background.")));
    }
    inputs.forEach(function (input) {
      var host = document.createElement("div"); input.parentNode.insertBefore(host, input.nextSibling);
      ReactDOM.createRoot(host).render(h(Preview, { input: input }));
    });
  }).catch(function () {});
})();
