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
