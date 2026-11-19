/* V107: React Date of Birth + Gender fields (compulsory everywhere). Upgrades every server-rendered [data-identity-fields] block:
   live, plain-language messages as the person types / leaves a box, and a guard that stops the form being submitted while either is
   missing or unrealistic (and stops double submission). The inputs keep their names, so the form still posts normally and the
   Flask backend (identity_rules.py - the same rules) validates again. This file loads React only when such a block exists. */
(function () {
  "use strict";
  var blocks = document.querySelectorAll("[data-identity-fields]");
  if (!blocks.length) return;
  var CDN = ["https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js", "https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"];

  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.crossOrigin = "anonymous"; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  function ensureReact() {
    if (window.React && window.ReactDOM) return Promise.resolve();
    return load(CDN[0]).then(function () { return load(CDN[1]); });
  }

  // the same rules as identity_rules.py
  function validateDob(raw, minAge) {
    raw = (raw || "").trim(); if (!raw) return "Date of Birth is required.";
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw); if (!m) return "Date of Birth is not a valid date - use the date picker.";
    var d = new Date(+m[1], +m[2] - 1, +m[3]); if (d.getFullYear() !== +m[1] || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[3]) return "Date of Birth is not a valid date.";
    var now = new Date(); if (d > now) return "Date of Birth cannot be in the future."; if (+m[1] < 1900) return "Date of Birth is not a sensible date.";
    var age = now.getFullYear() - d.getFullYear() - ((now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) ? 1 : 0);
    return age < minAge ? "Date of Birth is not realistic - must be at least " + minAge + " years old." : "";
  }
  function validateGender(v) { return v === "M" || v === "F" ? "" : "Gender is required. Choose Male or Female."; }

  ensureReact().then(function () {
    var React = window.React, h = React.createElement;
    function Fields(p) {
      var s0 = React.useState(p.dob), dob = s0[0], setDob = s0[1];
      var s1 = React.useState(p.gender), gender = s1[0], setGender = s1[1];
      var s2 = React.useState({ dob: false, gender: false }), touched = s2[0], setTouched = s2[1];
      var eDob = validateDob(dob, p.minAge), eGen = validateGender(gender);
      var ref = React.useRef(null);
      React.useEffect(function () {
        var form = ref.current && ref.current.closest("form"); if (!form) return;
        var guard = function (e) {
          if (form.dataset.submitting === "1") { e.preventDefault(); return; }       // no accidental double submit
          if (eDob || eGen) {
            e.preventDefault(); e.stopImmediatePropagation(); setTouched({ dob: true, gender: true });
            var first = ref.current.querySelector(eDob ? "input" : "select"); if (first) first.focus();
            return;
          }
          form.dataset.submitting = "1";
          form.querySelectorAll('[type="submit"]').forEach(function (b) { b.disabled = true; });
          setTimeout(function () { form.dataset.submitting = ""; form.querySelectorAll('[type="submit"]').forEach(function (b) { b.disabled = false; }); }, 8000);
        };
        form.addEventListener("submit", guard, true); form.noValidate = true;
        return function () { form.removeEventListener("submit", guard, true); };
      }, [eDob, eGen]);
      var showDob = touched.dob && eDob, showGen = touched.gender && eGen;
      return h("div", { className: "row g-3 identity-fields", ref: ref },
        h("div", { className: "col-12 col-md-6" },
          h("label", { className: "form-label", htmlFor: p.uid + "_dob" }, "Date of Birth ", h("span", { className: "text-danger", "aria-hidden": "true" }, "*")),
          h("input", { type: "date", id: p.uid + "_dob", name: "date_of_birth", className: "form-control" + (showDob ? " is-invalid" : touched.dob ? " is-valid" : ""), required: true, min: "1900-01-01", max: p.max,
            value: dob, "aria-invalid": showDob ? "true" : "false", "aria-describedby": p.uid + "_dob_msg",
            onChange: function (e) { setDob(e.target.value); }, onBlur: function () { setTouched(Object.assign({}, touched, { dob: true })); } }),
          h("div", { className: "invalid-feedback", id: p.uid + "_dob_msg", role: "alert" }, showDob ? eDob : "")),
        h("div", { className: "col-12 col-md-6" },
          h("label", { className: "form-label", htmlFor: p.uid + "_gender" }, "Gender ", h("span", { className: "text-danger", "aria-hidden": "true" }, "*")),
          h("select", { id: p.uid + "_gender", name: "gender", className: "form-select" + (showGen ? " is-invalid" : touched.gender ? " is-valid" : ""), required: true, value: gender,
            "aria-invalid": showGen ? "true" : "false", "aria-describedby": p.uid + "_gender_msg",
            onChange: function (e) { setGender(e.target.value); setTouched(Object.assign({}, touched, { gender: true })); }, onBlur: function () { setTouched(Object.assign({}, touched, { gender: true })); } },
            h("option", { value: "" }, "Select gender…"), h("option", { value: "M" }, "Male"), h("option", { value: "F" }, "Female")),
          h("div", { className: "invalid-feedback", id: p.uid + "_gender_msg", role: "alert" }, showGen ? eGen : "")));
    }
    blocks.forEach(function (el) {
      var dobIn = el.querySelector('input[name="date_of_birth"]'), genSel = el.querySelector('select[name="gender"]');
      var host = document.createElement("div"); el.parentNode.replaceChild(host, el);
      ReactDOM.createRoot(host).render(h(Fields, { dob: dobIn ? dobIn.value : "", gender: genSel ? genSel.value : "", minAge: parseInt(el.getAttribute("data-min-age"), 10) || 0,
        uid: (dobIn && dobIn.id ? dobIn.id.replace(/_dob$/, "") : "idf"), max: dobIn ? dobIn.getAttribute("max") : "" }));
    });
  }).catch(function () { /* CDN blocked: the server-rendered fields + backend validation still work */ });
})();
