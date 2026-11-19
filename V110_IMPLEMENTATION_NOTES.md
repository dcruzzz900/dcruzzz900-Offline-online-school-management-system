# V110 - React form layer, Date of Birth on result sheets, whole-package audit
Everything in V107-V109 still applies. V110 = V109 + the items below.

## 1. Date of Birth on the result sheet (ON/OFF)
* Result Display Settings > **Student details** > **Show Student Date of Birth** (default ON). Migration `result_show_dob_v110` adds `result_display_settings.show_dob`.
* Shown as DD/MM/YYYY on: the per-term result sheet (preview, print), the cumulative / annual sheet (screen, print) and the reportlab PDF fallback
  (both the termly and cumulative builders). A student with no recorded Date of Birth gets no empty box.
* Published results keep the settings they were published with (existing rule): sheets published before V110 do not gain a Date of Birth box.

## 2. Print = Download
* Already true by design when Chromium is present: `html_pdf.py` prints the SAME `result_print.html` + `result-sheet.css` the browser prints.
  Railway installs Chromium (`nixpacks.toml`). `result-sheet.css` and the print documents contain no dark-mode rule or theme stylesheet (now asserted by a test),
  so Light / Dark mode cannot change a printed or downloaded sheet.
* Only if Chromium is missing does the older reportlab builder run; it is a second renderer and is NOT pixel-identical. Keep Chromium installed in production.
  (Chromium is not available in the build sandbox, so the Chromium path was not exercised here; the fallback path was.)

## 3. Shared React form layer (`static/js/react-ui/forms.js`, `static/css/hub-forms.css`)
* Loaded on every signed-in page. It upgrades every server-rendered POST form automatically (staff, student, parent, admissions, attendance, subjects,
  timetable, profiles, theme & branding, school settings, materials, promotion, approvals, roles, terms, classes ...). Each form keeps its own action URL,
  CSRF token and field names, so it posts to the SAME Flask route: login, role permission, tenant isolation, business rules and database validation are unchanged.
* Frontend validation (required, pattern, min/max, length, e-mail, URL, number, date, `data-match`), inline field marks plus a summary; the server validates again.
* Duplicate-submit guard (one request in flight; buttons lock and show "Saving..."), loading / success / error banners, server flash messages are read and shown,
  typed input is kept when the server refuses, expired session and network failure have their own messages, file responses download without leaving the page.
* A successful save shows a toast on the page it lands on. If the server re-renders the same URL (its own field errors), that page is shown exactly as before.
* Opt out with `data-no-hub` (already set on score entry, AI, reports, broadsheet, cumulative and results-list forms). Forms with an inline `onsubmit`, a `target`
  or GET method are skipped. New React forms can reuse `window.SchoolHubForms` (Field, SelectField, FormStatus, SubmitButton, useSubmit).

## NOT done
* This is an enhancement layer over the existing forms, not a rewrite of each screen into a JSON-API-driven React page. Rewriting ~150 forms that way would change the
  business logic you asked to keep. Individual screens can be converted one by one on top of the same components.
* **School fees management**: there is no fees module (no fee structures, invoices or payments; see V109 notes). A form needs a real module and tables first.
* The form layer was syntax-checked, its helpers unit-tested in Node and the server side tested, but it has NOT been exercised in a real browser here.
  Click through: staff registration, student registration, a settings save, an invalid entry, a double click, and a signed-out session.

## Audit of the whole package
* All 183 templates compile; every `url_for` endpoint and every static file reference resolves; every `.py` file compiles; JS files pass `node --check`.
* 444 GET requests across all routes as School Admin and Teacher returned no server error.
* `tests/v110_scenarios.py` (28 checks) + `tests/js/forms_helpers_test.js` (22 checks); earlier suites re-run, see the release summary.

## V111 addendum (same package)
* **Next Term Resumes**: Sessions & Terms has a new "Next Term Resumes" box per term (migration `term_next_resumes_v111`, `terms.next_term_resumes_date`).
  One rule everywhere (`db.resolve_next_term_resumes`): the student's own date, else this admin-set date, else the following term's own resumption date.
  Used by the termly sheet (preview, print, PDF) AND the cumulative sheet (screen, print, PDF). Works for Third Term even before next session exists.
  Saving a date switches "Show Next Term Resumes" on (the message says so). Published sheets pick up date changes (date is not frozen with the design).
* **Mobile header / logo / photos**: uploaded logos are now normalised (upright from EXIF, transparent margins trimmed, max 600px, PNG) and a bad file is
  refused without deleting the current logo; the profile-page preview can no longer overflow; the phone top bar clamps long school names/addresses and pads the
  logo; the on-screen result sheet header wraps on phones (print/PDF unchanged). Passport photos already used the 4:5 normaliser.
* Tests: `tests/v110_scenarios.py` now 47 checks. Not verified on a real phone: please view the profile page and a result sheet at phone width.
