# V115 — UI update

1. **Teachers & Staff**: the *Add a Teacher* form is collapsed; "+ Add Teacher" expands it (Close button inside). It stays open after a failed submit.
2. **Teacher dashboard layout** (desktop / tablet / phone): panel rows reflow using rem-based minimum widths, cards in a row share height with content centred,
   Quick Access last tile fills its row, attendance range buttons form a tidy grid, wide tables scroll sideways on phones instead of crushing columns.
3. **Text size (A- / A+)**: panel/tile minimum widths are in rem, so larger text stacks panels earlier rather than squeezing. Top bar no longer pushes the avatar off-screen on phones at 130-150%.
4. **Student dashboard**: Attendance now sits immediately after Academic Performance.
5. **Announcements cards** (Admin, Teacher/staff, Registrar, Student, Parent, Super Admin): list ALL announcements addressed to the viewer (`announcement_feed`, announcements.py `feed_for`),
   including ones dismissed from the strip or beyond its limit of five; long lists scroll inside the card. Root cause of the old "No announcements": the macro was imported without `with context`.
   Dismissing a banner still hides it from the top strip only (tests v104/v107 updated accordingly).
6. **v106 headers everywhere**: Registrar and Super Admin dashboards use the v106 banner; `.page-heading`, `.page-head`, `.dashboard-header`, bare `<h1>` and the AI hero are styled like v106 headers (static/css/v115-layout.css, loaded last).
7. **Student mobile bottom menu**: Home / Results / Materials / Alerts / More (More sheet: AI Tutor, Timetable, Profile, Account, Logout); static/js/student-more.js.
8. **Fix**: db.py was missing `insert_returning_id` in its import, which crashed first-time database seeding.
9. Service worker cache version bumped to v115 (new CSS/JS are pre-cached; existing installs refresh).

Tests: `python tests/v115_scenarios.py` (new). All 52 scenario scripts pass.
