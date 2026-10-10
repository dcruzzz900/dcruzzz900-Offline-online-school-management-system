# V65 — bug fixes and enhancements

## Bugs fixed
1. **Student AI Consent "internal server error"** — root cause: the save passed `consent_status` to the audit logger twice (TypeError) and the route never committed. Now one writer (`record_ai_consent`) saves the record, appends a history event and writes the audit entry in one transaction. Validation (student must be in the school, status must be valid, consent needs the consenting person's name + relationship), duplicate-submission protection (unchanged status = no-op; button disables on submit), clear success/error messages, history table (who, relationship, previous → new, server time). The parent-portal consent uses the same writer.
2. **Duplicate staff signature** — the profile edit form no longer has a signature field; the Digital Signature card (upload / replace / remove / preview / use-on-sheets toggle) is the only one.
3. **Duplicate settings** — result-sheet options (accent, header, teacher/principal name + signature) no longer exist on Theme & Branding; the motto moved to School Profile; header/logo alignment left School Profile; the Cumulative / Annual toggle left Sessions & Terms. Result Display Settings owns all of them.
4. **Result PDFs/broadsheets differed from print** (earlier, v64) — now also covers the broadsheet; one-page fit was measured at the wrong width and a fixed print height clipped content (signatures cut off) — fixed.
5. **Passport** — shown whole (contain, centred, no extra border); neutral avatar when missing.
6. **Unreadable "Overall position" card** in three styles; **comment generators** wording (v64).

## Features
Password show/hide on every password field (accessible, mobile-sized, stays hidden by default) · Result Display Settings cards: Branding & layout (Logo position, Header text alignment — independent), School information (address / email / phone / motto toggles), Student details (+ Show Resumption Date), Comments & signatures (+ All Comments master switch), Cumulative / Annual Result · Resumption date per term on Sessions & Terms (shown only when switched on and set) · Timetable: period structure entered once and applied to selected days (breaks, names, live preview), single-period edits, copy one day to another with clash checks · Form-teacher drafts (Save Draft, status shown, locked once submitted/approved/published) · Dashboards: Academic workspace / School operations / Quick Actions no longer repeat each other · Domain ratings 1–5 shown with meanings everywhere · Ten structurally different result templates (CSS grid layouts: stacked, banner+strip, certificate order, left sidebar, two-column bottom, right rail, results-first minimal, 3-column ledger, card board, split) — all fit one A4 page.

## Migrations (automatic backup first: `instance/backups/pre-migration-*.db`)
* `staff_titles_v64`, `ai_consent_history_v65` (new columns on `student_ai_consent`, new append-only `student_ai_consent_events`)
* `result_settings_single_home_v65`: new switches on `result_display_settings` (`show_address/email/phone/motto/resumption_date/all_comments`, `text_align`); old single "contact" switch seeds address/email/phone; Theme-saved signature/name toggles are copied once into the authoritative table if never saved from the new page; `terms.resumption_date`. Old `schools` columns are left in place, unused.

## Files changed
app.py, db.py, html_pdf.py, pdf_utils.py, profile_routes.py, v62_routes.py, v64_spec.py, static/css/result-sheet.css, static/css/style.css, static/js/password-toggle.js (new), templates: _result_sheet, admin_dashboard, admin_school, admin_terms, ai_consent, base, broadsheet_print, profile_form, result, result_display_settings, result_print, theme_branding, timetable_edit_v2, timetable_setup_v2; tests: v65_scenarios.py (new), test_v65_behavior.py (new), v60–v64 scenarios adjusted for the intended behaviour changes.

## Tests
v65 146 checks · v64 104 · v63 107 · v62 248 · v61 292 · v60 213 · 45 contract tests — all pass. Includes PDF text checks, one-page fit for every style, 63-student broadsheet (3 landscape pages, header repeated, no one missing).

## Limits
* Mobile-browser printing could not be exercised here; the PDF/print page is the same HTML, and the PDF is produced server-side, so downloads do not depend on the phone's print engine. Browser "Print" on a phone depends on that browser.
* Without Chromium on the host (e.g. PythonAnywhere) PDFs fall back to the older layout.
* Venues/rooms exist in the timetable data model; teacher and class clashes are checked on copy, room clashes too.
* Cumulative / Annual calculations were not touched.
