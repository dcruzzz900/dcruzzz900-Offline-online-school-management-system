# V96 — Compact charts, last-week attendance, dashboard icons

You followed up on the V95 dashboard charts: *"The charts does not render well it's too
verbose... Let the chart increase in size as data input increases. Attendance trends should be
last week not 8weeks... Use beautiful icons on dashboard cards where necessary."*

## 1. Charts were rendering oversized — fixed

**Root cause:** every chart canvas had no height-constrained parent element. Chart.js's
`responsive: true` + `maintainAspectRatio: false` combination needs a parent with a real, stable
CSS height to measure against — without one, the chart had nothing reliable to size itself
against, which is what made the charts balloon ("too verbose") on your live site.

**Fix:** every canvas now sits inside a new `.chart-wrap` div with a fixed CSS height (200px for
the main charts, 160px for the smaller ones like Attendance Trend and Subject Scores). The chart
itself can no longer grow taller than that, on any page, regardless of how much data it's
showing.

## 2. "Let the chart increase in size as data input increases"

For charts whose category count can genuinely grow — Student Performance by Class, Enrolment by
Class Level, Subject Scores, Academic Performance trend — the `.chart-wrap` now sits inside a
horizontally-scrollable `.chart-scroll` container. A new `growWrap()` helper in
`dashboard-charts.js` measures how many bars/points the chart has and widens the wrap
proportionally (about 60–72px per category) whenever that's wider than the card itself — so a
school with 20 classes gets a wider, legibly-spaced chart you can scroll through, while a school
with 3 classes gets one that just fills the card. The chart only ever grows **wider**, never
taller — height stays fixed and compact in both cases, matching what "too verbose" was
complaining about.

The Gender Distribution donut and the Attendance Trend line don't use this — a donut is always 2
slices, and attendance is now always ≤7 days (see below), so neither one needs to grow.

## 3. Attendance Trend: last week, not last 8 weeks

Replaced the old weekly/8-week bucketing with daily buckets over the last 7 recorded days.
`_attendance_week_buckets()` → `_attendance_day_buckets()` in `app.py`; `school_attendance_trend()`
and `student_attendance_trend()` now default to `days=7` instead of `weeks=8`. Each day is
labelled with a short, readable string ("Mon 26") instead of a raw ISO date. Card headings
updated from "Attendance Trend (Last 8 Weeks)" to "Attendance Trend (Last Week)" on Admin/Teacher;
the Student/Parent sub-heading changed from "Last 8 weeks" to "Last week". Still present+late
counted as attended, matching the exact convention used everywhere else in the app.

## 4. Icons on dashboard cards

Added a small, dependency-free inline-SVG icon set (`templates/partials/dash_icons.html`, a
`dicon(name)` macro — no icon font, no external request) and a `.card-icon` badge style. Icons now
appear next to: Student/Class Performance, Gender Distribution, Attendance Trend, Enrolment by
Class Level (all 4 dashboards, role-appropriate), Top Performing Students, Recent Activities, and
School Result Performance Trend. Kept deliberately restrained — not every card title needed one
(quick-action buttons, workspace tables, etc. were left alone) so the dashboard doesn't look
over-decorated.

## Files touched

- `app.py` — `_attendance_day_buckets()` replaces `_attendance_week_buckets()`;
  `school_attendance_trend()` / `student_attendance_trend()` default to `days=7`.
- `static/js/dashboard-charts.js` — new `growWrap()` helper, called from the 4 charts whose
  category count can grow.
- `static/css/style.css` — `.chart-wrap`, `.chart-wrap-sm`, `.chart-scroll`, `.card-icon`,
  `.icon-title` rules replace the old unconstrained `.chart-card canvas{max-width:100%}` rule.
- `templates/partials/dash_icons.html` — new, the icon macro.
- `templates/admin_dashboard.html`, `templates/teacher_dashboard.html`,
  `templates/student_dashboard.html`, `templates/parent_dashboard.html` — chart markup rewrapped
  in `.chart-wrap`/`.chart-scroll`, headings updated, icons added, `attendanceLabels` now reads
  the new `label` field instead of the old `week_start` field.

No database migration. No change to result sheets, broadsheets, or PDFs — dashboards only, same
as V95's scope.

## Testing

- New `tests/v96_scenarios.py` (44 checks, all passing): confirms the chart-wrap/chart-scroll
  markup is actually present around each scalable chart, confirms the fixed-size donut/attendance
  wrappers are unchanged, confirms icon badges are present on the expected titles, confirms the
  "Last Week"/"Last 8 Weeks" heading text on every dashboard, and directly unit-tests the new
  daily-bucket helper's 7-day cap (10 days of recorded attendance → only the most recent 7 come
  back, correctly ordered, with the real trailing absence still reflected).
- Updated `tests/v95_scenarios.py`'s one attendance-bucket-count assertion (3 weekly buckets → 4
  daily buckets) to match the now-correct V96 behavior — same "fix the stale assumption, don't
  weaken the check" precedent used in every prior round that changed existing behavior.
- Full regression: all 37 suites (`tests/v60_scenarios.py` through `tests/v96_scenarios.py`),
  1,929 checks total, 0 failures.

## Installing on PythonAnywhere

No database changes this round. Replace these files:

- `app.py`, `static/js/dashboard-charts.js`, `static/css/style.css`,
  `templates/admin_dashboard.html`, `templates/teacher_dashboard.html`,
  `templates/student_dashboard.html`, `templates/parent_dashboard.html`
- **New file:** `templates/partials/dash_icons.html`

Then reload your web app from the **Web** tab. No migration to run.
