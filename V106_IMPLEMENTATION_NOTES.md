# V106 — gender on result sheets, shared gender panel, Bootstrap + brand + light/dark, three React pieces

## What changed
1. **Gender on the result sheet.** New Result Display Settings switch "Show Student Gender" (Student details; ON by default).
   Shown on the terminal sheet, the annual/cumulative sheet and both PDFs. Migration `result_sheet_gender_v106` adds the column.
2. **One Gender Distribution panel.** `templates/partials/gender_panel.html` (+ `gender_panel_data()` in app.py, `static/css/gender-panel.css`)
   is the School Administration dashboard's donut, now inherited unchanged by the Teacher dashboard, School Analytics and Reports & Analytics.
   The old Chart.js gender donut / "Students by gender" card are removed from those pages.
3. **Bootstrap 5.3.3** (pinned CDN, same approach as Chart.js) in `base.html`. `tools/bootstrapify_templates.py` moved forms, selects, tables
   (wrapped in `.table-responsive`) and buttons to Bootstrap classes in 144 templates (idempotent; skips result sheets, print/PDF templates and
   sign-in screens). Flash messages are dismissible Bootstrap alerts (still carry the `flash flash-<category>` classes).
4. **Theme + branding everywhere, light/dark.** `static/css/theme.css` maps the school's Theme & Branding colours to Bootstrap and the legacy
   tokens (with readable button text computed per colour), honours the sidebar/header style settings, and defines light/dark surfaces.
   `static/css/theme-dark.generated.css` is generated from the app stylesheets by `tools/build_dark_css.py` (re-run it after editing CSS).
   Toggle: top bar (staff) and a floating button on sign-in/other shells; choice stored in `localStorage` key `sh-theme`; follows the OS when unset.
   Printing is always light; result-sheet paper is never darkened.
5. **React** (UMD 18.3.1 from the CDN, `React.createElement` — no build step; `static/js/react-ui/`):
   - `dashboard-filters.js` — term/class selectors on Teacher dashboard and School Analytics; `GET /api/dashboard/analytics`; charts update in
     place (`schoolHubDashboardCharts.update`), gender panel + top-students swap in as server markup, URL keeps `?term_id=&class_id=`.
   - `result-preview.js` — Result Display Settings: form left, sticky live preview right. Colours / paper / orientation apply instantly; show/hide
     switches re-render the real `_result_sheet.html` via `POST /api/result-display-settings/preview` (nothing saved). ON/OFF captions, unsaved-change counter, Reset.
   - `score-entry.js` — live totals/grades, instant max-score validation, per-row save status; `POST /api/scores/<class>/<subject>/row`.
     Saves when focus leaves a valid row (not per keystroke, to keep the audit trail clean), per-row Save, Save all, Ctrl+S, Enter moves down a column.
     The classic server form stays as the no-JavaScript fallback.

## Security notes for the new endpoints
All three are `login_required`, tenant-scoped, and need the `X-CSRF-Token` header. The score row API reuses `save_score`, `score_range_errors`, the
assigned-teacher check, the publication lock (423) and the reopened-needs-reason rule (422) exactly as the classic form; it additionally rejects NaN/inf.
The dashboard API refuses classes outside the user's visible set (403) and unknown terms (404).

## Deploy / operations
* No new Python dependencies. The browser needs internet for Bootstrap and React (same as Chart.js already did); pages degrade to the app's own CSS
  and the classic score form if a CDN is blocked. SRI hashes are not set (pinned exact versions instead) — add them if you want.
* Static files have no cache-busting; after deploying, a hard refresh may be needed on devices that cached the old CSS/JS.

## Tests
`tests/v106_scenarios.py` (70 checks). Updated for intentional markup changes: v61, v65, v77, v88, v95, v96, v101, v104 (flash regexes, class
presence instead of exact `class="rt"`, shared gender panel instead of the old Chart.js card) and `test_online_first_stability.py`.
Full suite at release: 44/44 scenario scripts, 73/73 contract tests.

## Known limits
* Not verified with the real CDN files: tested against local stand-ins (Bootstrap 5.3.2, React 19 bundle, a fake Chart.js). Chart appearance in dark mode is unchecked.
* Dark mode was visually reviewed on the dashboard, students, score entry, settings and analytics pages only; the rest is generated and untested by eye.
* Dashboard filters cover the two Chart.js staff dashboards (not parent/student, not the main admin dashboard).
* Setting thumbnails on the settings page show saved settings (colours update live); the main preview is fully live.
