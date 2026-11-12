# V95 — Real analytics charts on every dashboard

You sent two screenshots of a reference dashboard — grouped bar charts, a gender donut, a weekly
attendance line, an enrolment bar chart, a Recent Activity feed, a Top Performing Students table —
and asked: *"My school hub admin dashboard should look analytical exactly like this. All charts
must show exactly. Extend to students dashboard, staff dashboard and parent dashboard."*

Done. Every number on every chart is real, computed data from your database — nothing is mocked.

## Admin Dashboard — the full set, school-wide

- **Student Performance by Class** — grouped bars, Average % and Pass Rate % per class.
- **Gender Distribution** — a donut, Male vs Female (your existing Boys/Girls count card is
  still there too, just above it).
- **Attendance Trend (Last 8 Weeks)** — a line chart, weekly attendance rate.
- **Enrolment by Class Level** — a bar chart, active students per class.
- **Recent Activity** — this already existed (V90); unchanged.
- **Top Performing Students** — new: the top 5 students school-wide, ranked by their own average
  score this term.

## Teacher / Staff Dashboard — the same chart set, scoped to what they can see

Identical charts and the same Top Performing Students table, but every number is restricted to
only the classes that staff member actually has access to — never the whole school. A class they
have no assignment in never appears in any of their charts (verified by test).

## Student & Parent Dashboards — the role-appropriate version

A single student (or their parent, for the linked child) doesn't have a "class" to compare or a
gender to distribute, so rather than forcing the same 4 charts onto one person, these dashboards
get:

- **Academic Performance** — now a real line chart (My average % vs. Class average %, by
  published term) in place of the old plain bar strip, still respecting the exact same
  publication gate it always has — an unpublished term still never appears.
- **Subject scores this term** — a new bar chart of the student's own CA1/CA2/[CA3]/Exam/Total
  for the latest published term.
- **Attendance Trend (Last 8 Weeks)** — the same weekly line chart as Admin/Teacher, scoped to
  just that one student.

Gender Distribution and Enrolment by Class Level are deliberately **not** added to Student/Parent
— a donut of one person's own gender, or a bar chart of one class's headcount, isn't meaningful
information for a student or their parent to see about themselves. The test suite checks this
boundary explicitly, not just by omission.

## How it's built

- **Chart.js** (via CDN, one pinned version — `4.4.4`) renders every chart client-side from small
  JSON arrays each dashboard template already embeds server-side. No chart image is rendered on
  the server, so results and PDFs are completely unaffected by this round.
- A new shared `static/js/dashboard-charts.js` holds the actual Chart.js setup (colors, chart
  types, options) in one place, so Admin/Teacher/Student/Parent draw visually consistent charts
  rather than four separately hand-tuned ones. Each dashboard template passes it only the data it
  actually has; a chart with no relevant canvas on a given page is simply skipped, never an
  error.
- Five new data helpers in `app.py`:
  - `all_classes_performance()` — every class's average score + pass rate, including a class with
    nothing assessed yet (shown as a real gap, never a false zero) — feeds the class-performance
    bar chart specifically, as distinct from the existing `ranked_class_performance()` (used for
    the High-Performing/Needs-Improvement panels), which deliberately leaves an unassessed class
    out entirely so it's never unfairly flagged. Two different, correct behaviors for two
    different uses of the same underlying numbers.
  - `enrolment_by_class()` — active-student headcount per class.
  - `school_attendance_trend()` / `student_attendance_trend()` — weekly (Monday-start)
    attendance-rate buckets, present+late counted as attended, matching the exact convention the
    existing `student_attendance_stats()` already uses.
  - `top_performing_students()` — every assessed student ranked by their own overall average this
    term, reusing the same `compute_total`/`grade_for` convention the result sheet and
    `class_term_result_stats()` already use.
- `templates/base.html` gained one new, empty `{% block extra_scripts %}` right before `</body>`,
  so a page that needs Chart.js can load it without adding ~200KB of JS to every other page in the
  app that doesn't use charts.

## Testing

- New suite `tests/v95_scenarios.py` (30 checks, all passing): parses the real JSON each
  dashboard template embeds (the same data Chart.js itself would consume) and checks it against
  real fixture data — a class with real scores shows its true average, a class with nothing
  assessed shows a genuine gap rather than 0%, a staff member's charts never include a class
  they can't see, an unpublished term never appears in a student's/parent's Academic Performance
  chart, and Gender/Enrolment charts are confirmed absent (not just unmentioned) from the
  Student/Parent dashboards. Tenant isolation checked for Admin.
- Full regression run: **all 36 test suites (`tests/v60_scenarios.py` through
  `tests/v95_scenarios.py`), 1,885 checks total, 0 failures.**
- Found and fixed one real bug while finishing this round: the new Top Performing Students table
  on both Admin and Teacher dashboards called `student_full_name(...)`, a template helper that
  wasn't actually being passed into those two `render_template()` calls — caught immediately by
  the regression suite (several V89/V90 checks failed with a 500 error) rather than shipped.

## Installing on PythonAnywhere

No database changes this round. Replace these files (or extract the new zip over your install):

- `app.py`, `templates/base.html`, `templates/admin_dashboard.html`,
  `templates/teacher_dashboard.html`, `templates/student_dashboard.html`,
  `templates/parent_dashboard.html`, `static/css/style.css`
- **New file:** `static/js/dashboard-charts.js`

Then reload your web app from the **Web** tab. No migration to run. Open the Admin Dashboard and
confirm all 4 charts render with real numbers, then check a Teacher/Student/Parent login to see
their own scoped versions.

## What I left out, and why

- **No new charting on the dedicated per-class Results workspace, broadsheets, or any result
  sheet/PDF** — this round is dashboards only, matching exactly what you asked for.
- **No historical multi-session trend** (e.g. a year-over-year line) — every chart here is scoped
  to the current session/term, consistent with every existing trend chart already in this app
  (`school_performance_trend`, the class trend sparkline, etc.) for the same reason noted back in
  V89's own notes: a true multi-year trend needs its own look at how much historical session data
  schools actually keep, not something to guess at here.
