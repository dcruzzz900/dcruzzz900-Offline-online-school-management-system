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

## Update — six sample-inspired result templates
Built from the seven sample report cards supplied (the green and blue "Demo International" samples are the same layout, so they are one template whose colour follows the Result Display accent). Names are descriptive, not school names; no school's branding, logo or wording is copied — each sheet shows the signed-in school's own data.

| Template id | Layout it reproduces |
|---|---|
| `boxed_grey_card` | bold centred school name, ruled student-details box, dark-grey subject table with rotated headings plus class average / highest / lowest, traits and score-range tables, report rows |
| `assessment_dossier` | letter-spaced title band, fill-in style student lines, numbered subjects (1st CA / 2nd CA / Exam / Sum), 5-4-3-2-1 tick grids, remark lines |
| `peach_terminal_sheet` | peach headers with rotated column titles, attendance + grade-analysis + grade-scale side panels, performance-summary box, remark rows with signatures |
| `green_cumulative_report` | framed header with passport, green section bars, term **and cumulative** columns (when Cumulative/Annual is ON), remarks beside tick-box domains |
| `progress_report_card` | colour header band, student card with passport, max / min / average columns with grade chips, academic analysis, feedback quotes, ratings side panel |
| `clean_midterm_report` | centred minimal header, details list beside the passport, light table, summary and attendance panels, remarks box |

New real data computed for them (nothing invented): class average, highest and lowest per subject, grade distribution, overall grade, total obtainable, gender/date of birth, cumulative per-term values.
Every sheet honours Result Display Settings (logo, passport, address/email/phone/motto, resumption date, All Comments, signatures, grading key, domains, subject position, CA3), prints/PDFs through the same Chromium path, and fits one A4 page.

Not reproduced because the system has no such data/module: the NIN field, the "Financial outlook (next term)" fees box and the QR security-verification code on the Demo International samples, and "Vacation date". Tell me if you want those added as real features.
Without Chromium on the host the PDF falls back to the older builder, which does not have these six layouts.

Tests: v65 now 203 checks (adds: each sample renders in preview/print/PDF, one page, real data, tenant-safe, toggles, All Comments, cumulative columns on/off).

## Update — one sign-in screen
`/login` is now a single form for administrators, staff and parents (username / email / phone + password, optional School ID, show/hide password, forgot-password and activation links, signup links, and a pointer to the separate Student login). The role-card chooser and pop-up were removed. `/admin/login`, `/staff/login` and `/parent/login` redirect to it. The server already identified the account type itself (parent first, then staff/admin), so each user lands on their own dashboard; a "portal" choice can no longer matter. Platform (Super Admin) and Student sign-in remain separate by design. Tests: v65 has 215 checks (adds unified-screen, redirects, parent sign-in by username/email/phone, wrong-password message, no privilege escalation through a claimed portal).

## Update — "My School Hub" icon and phone install
* Icons regenerated with the app name under the artwork: `icon-192.png`, `icon-512.png` (rounded, transparent corners), `icon-maskable-192.png`, `icon-maskable-512.png` (full-bleed; artwork and wording kept inside the 80% safe zone so circular/squircle masks never cut them), and `apple-touch-icon.png` (180×180, for iPhone "Add to Home Screen").
* `manifest.json`: name and short name "My School Hub", standalone display, start page from the site root, navy splash colour matching the icon, four icons (any + maskable at 192 and 512). Icon URLs carry `?v=3` so phones fetch the new artwork.
* `service-worker.js` is now a **network-only** worker: it caches nothing, answers every page load from the server, and shows a plain "cannot reach the server" page if there is no connection (deleting caches left by older offline builds). It is registered by `online-only.js`. This keeps the online-only behaviour while letting phones install the site as an app.
* iOS meta tags added (app title, standalone, status bar).
* Verified with Chromium's own installability check against a local server: manifest parses with no errors, no installability errors, worker registers.
* Phones need HTTPS (Railway provides it). Already-installed shortcuts keep the old icon until removed and re-added.
