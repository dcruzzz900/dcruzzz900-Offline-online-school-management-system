# V112 – v106 Modern UI/UX ported into v111
## What changed
* `static/css/modern.css` = the v106 design system (verbatim; only the two px font-sizes were made scale-aware so the A-/A+ control still works).
* `static/css/modern-compat.css` (new) maps v111 markup (Bootstrap + `.stat-box`, `.page-heading`, `.ad-*`) onto the v106 look, neutralises legacy shell rules, keeps school Theme & Branding colour (`--theme-primary`) and Light/Dark mode.
* `static/js/modern-shell.js` = v106 drawer JS + Mobile "More" tab + active-link marking. `shell-ui.js` stands down for the staff drawer.
* `templates/base.html`: staff shell (drawer sidebar, v106 top bar with search/bell/role chip/avatar, bottom tabs), parent + student shells (top bar + tab strip), Super Admin shell (drawer). All Jinja logic, role checks, endpoints, CSRF, search ids, live clock, flashes unchanged. Sidebar also gains v106 entries: Result Display, Additional Result Fields, School Fees.
* NEW screen `School Fees` (`/admin/school-fees`, `admin_school_fees`): edits the existing `school_fee_summary` totals that feed the dashboard card. v111 still has NO per-student invoice/payment ledger – not invented.
* Tests updated where they asserted the old shell markup (v61, v62, v75, v104, v105); new `tests/v112_modern_smoke.py`.
## Not done / verify
* Per-page markup of the other ~170 templates was NOT rewritten one by one; they get the v106 look through the shared layer. Pages with heavy custom CSS (result sheets, timetable, broadsheet, platform billing screens) need a visual pass.
* v106 mock data (names, numbers) was deliberately not copied; every figure comes from v111 queries.
* Result sheets/prints are untouched (print CSS excludes the shell).
* Checked in Chromium only for dashboard, students, login at 1280/390px. Click through every role on a real phone.
## Second pass (visual)
Fixed: phone table/card overflow, undefined grid utilities (`grid-3/4`, `kpi-grid`...), parent/student/platform top bars, floating text-size/theme widget overlapping portal headers. Seen in Chromium: admin dashboard, students, analytics, timetable, login, student dashboard, Super Admin dashboard (desktop + phone). Platform charts need Chart.js from a CDN (unchanged from v111). Parent dashboard + My Children (desktop + phone), result sheet, broadsheet checked too. Also fixed a pre-existing 'Staff Staff Attendance' label on the parent child pages.
Dark mode checked on dashboard + students (fixed panel titles and theme button).
Dark mode also checked on student dashboard, Super Admin schools, parent My Children (fixed platform role chip).
Fixed a stray </div> in platform_billing.html that collapsed the layout under the new shell; smoke test now guards against it. Theme colour inputs given real height.
Result sheet keeps dark-on-paper text in dark mode (.rs-screen-wrap).

## Enhancement round (teacher dashboard, admin tiles, typography, floating control)
1. **Teacher Quick Access = exactly 7 tiles** (Score Entry, Take Class Attendance, Results Approval, Show Results, View Timetable, My Profile, Learning Materials). Every other role-aware shortcut (Class Register, Domain Ratings, Class Teacher Comments, Submit Results for Review, Registrar actions...) is kept in a collapsed "More tools for your role" panel — nothing removed.
2. **Teacher analytics (real DB data, scoped to the teacher's own classes):** Subject Performance, Pass/Fail Distribution, Top Performing Students, Recent Activities, plus Class Performance, Attendance Trend, Grade Distribution. Charts are server-drawn SVG, so they work offline. A class the teacher cannot see never leaks in (tested).
3. **Admin Quick Access:** 8 tiles by default, `View All (18)` / `View Less` (state remembered on the device); all 18 v111 shortcuts kept.
4. **Typography:** base text 17px (16px phones), still scaled by A-/A+ (90–150%). The font-scale rules now live in `modern-compat.css`, because v106 pages no longer load `theme.css` (before this, A+/A- did nothing on v106 pages).
5. **Floating Display settings** (`partials/floating_settings.html`, `static/js/floating-settings.js`): draggable (mouse/touch/pen, Shift+Arrows), tap opens text-size + light/dark + reset-position; always clamped on-screen; on every page including sign-in. The old header/theme-fab copies were removed (one control only).
6. **Persistence:** size + theme saved per person on the server (`/api/preferences`) and per device; control position saved per device as screen fractions.
7. **Responsive:** verified no horizontal overflow on 70 pages at 1280/820/390px and at 150% text on 820/390px.
8. Shared v106 banner partial keeps the v107 school-timezone clock (tz + UTC anchor) without React. Shared gender panel and top-students table now emit v106 markup, so the React dashboard filters keep working.
9. **Tests:** `tests/v112_enhancements.py` (49 checks) + all scenario suites v60–v110 pass (assertions tied to the old dashboard markup were updated). pytest-style `test_*.py` files were not run (pytest not installed offline).

## Round 3 (Next Term Resumes, admin charts, teacher clean-up, dark mode, layout)
* **Next Term Resumes fixed:** a brand-new school has no saved Result Display row, so saving the date never switched "Show Next Term Resumes" on (the sheet silently omitted it). Saving the date now creates the settings row and switches it on. Every sheet path (terminal result, print, PDF, parent/student, cumulative, batch email) shares `build_result_data`, so all students get it.
* **Admin dashboard:** Gender Distribution removed (the Students card still shows the male/female split). New **Attendance Trend** line chart — Students/Staff × This week / Last week / Last month (by week) / Last year (previous calendar year, by month); **Enrollment Trend** selectable By term / By year; new **Enrolment by Class Level** chart. All data is computed server-side from `attendance_records`, `staff_attendance`, `enrollments`, `classes.level`; charts are drawn by `static/js/sh-charts.js` (offline, no CDN).
* **Teacher dashboard:** Score Entry tile opens the new **My Teaching Workspace** page (`/teaching-workspace`); the workspace, Results workspace, Class Result Performance, "More tools" and the AI cards were removed from the dashboard; Pass/Fail and Subject Performance now appear once (v111's canvas duplicates removed; the class/term filter still updates the v106 panels via `teacher-panels.js`); Results Approval tile replaced by **Submit Results for Review**; Attendance Trend is a line chart; v106 **My Classes** table added; Top Performing Students + Recent Activities moved to the bottom. The role shortcuts that were in "More tools" (Class Register, Domain Ratings, Class Teacher Comments, Registrar actions…) are kept on the My Teaching Workspace page so no feature is stranded.
* **Dark mode:** full pass. Automated audit (`tests/v112_dark_audit.py`, `tests/v112_dark_audit_portals.py`) checks every visible text node against its real background (WCAG 4.5:1 / 3:1 large): 0 failures on 235 admin/teacher/Super Admin page loads and the student/parent portals. Legacy light backgrounds get generated dark counterparts (`modern-dark-legacy.css`). The result-sheet paper intentionally stays light.
* **Layout:** `tests/v112_layout_sweep.py` loads key pages at 6 widths (1280–320px) × 3 text sizes (90/100/150%) and fails on horizontal overflow, off-screen or clipped content (including `overflow:hidden` clipping) — 0 problems on 216 combinations. It caught and fixed a clipped period selector and a banner/KPI clip at 320px + 150%.

## Round 4 (more v106 screens)
Converted to the exact v106 markup with live v111 data (legacy CSS no longer loads on them): **Student dashboard**, **Parent dashboard**, **Classes**, **Subjects**, **Teachers & Staff**, **Students**, **Parents**. Every v111 form, action, CSRF token, permission check and shortcut was kept.
* Student: average, class position (same builder as the result sheet), per-subject score bars (unscored subjects stay gaps, never zeros), your-average-vs-class line, attendance KPIs + last-week line, published-results table, all 10 v111 shortcuts.
* Parent: a card per linked child (latest average + position), term-average and subject charts, subject table with grade/remark, attendance, quick links, all v111 shortcuts; only linked children are selectable.
* Admin lists gain the v106 KPI row, search/filters (`static/js/table-filter.js`) and real counts (students/subjects per class, teachers/classes per subject, linked children per parent, subjects/classes per staff member).
* Shared pieces restyled for v106 pages: identity fields (DOB/gender), form labels/selects, help toggles. Dark-mode audit: 0 failures on admin, teacher, platform and both portals; layout sweep: 0 problems.
* Tracker: `UI_V106_CONVERSION_STATUS.md`.
