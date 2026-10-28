# V88 — Dashboard Analytics, Phase 2: Gender & Enrolment Statistics

You sent a big new requirements document — "My School Hub: Complete Feature Enhancement
Specification" — covering analytics for all five dashboards (Admin, Teacher, Student, Staff,
Parent) plus a full paper-size/orientation overhaul for result sheets. It's a genuinely large
piece of work (the document itself lays out 8 phases), so — same as every other big requirements
doc on this project — I'm building and delivering it one phase at a time rather than guessing at
all of it in one shot. This round is **Phase 2 only: Gender & Enrolment Statistics**, for the
Admin and Teacher dashboards. Everything else in the document (performance trends, high/low
performing classes, recent activities feeds, Student/Staff/Parent dashboard analytics, and the
whole paper-size section) is still queued — see "What's next" below.

## What's in this round

**Admin Dashboard** — one combined card, right under the existing Students/Staff/Classes/Subjects
row, showing:
- **Boys** and **Girls**, each with its own icon and label, in a single card (not two separate
  cards — the spec was explicit about that).
- A third "Unspecified" figure only appears if your school actually has any student with no
  gender recorded — most schools will never see it.

**Teacher Dashboard** — the existing "Results workspace" table (where you already see your
classes with Broadsheet/Terminal Results buttons) now also shows **Students / Boys / Girls** for
every class you have access to, right there in the same table — no new page to visit.

## How the numbers are calculated (so you can trust them)

- Pulled live from the real `students` table every time the dashboard loads — nothing cached,
  nothing precomputed. Register a student, transfer one out, or correct someone's gender, and the
  very next dashboard load reflects it.
- Only counts **active** students (`is_active=1`) — a transferred or withdrawn student (however
  your admin screens mark that) drops out of the count immediately, the same way they already drop
  out of the main "Students" counter.
- Boys and Girls counts only ever include `M`/`F` — a student with no gender on file is excluded
  from both, exactly as the spec required, and only shows up in the separate "Unspecified" figure
  so the three numbers always add up to the real total.
- Every query is scoped to the signed-in school (and, on the Teacher Dashboard, to that specific
  class) the same way every other number on these dashboards already is — I reused the project's
  existing tenant-scoping pattern rather than inventing a new one, and tested it directly: a second
  school's admin sees only their own figures, never another school's.

## What I deliberately did NOT build this round

- **Enrolment trend charts** (monthly/termly, admissions/withdrawals/transfers over time) — this
  is 1B/2B in your document. It needs its own careful look at what historical enrolment data this
  app actually keeps today (so I don't end up fabricating trend lines from thin data), which is
  real work on its own — next round.
- **Performance trends, high/low-performing classes, pass/fail stats** (1C/1D/1E, 2C/2D) — these
  depend on reading real scores against your grading config correctly, which I want to give its own
  focused round rather than rushing alongside this one.
- **Recent Activities panels** (1F/2E and the Student/Staff/Parent equivalents) — the app actually
  has *two* separate audit-logging systems already (a simple one and a richer one used by newer
  features). Before building "Recent Activities" I want to settle which one new activity types
  should feed, so the feature doesn't end up reading from the wrong place. That decision, plus the
  actual panels, is next.
- **Student/Staff/Parent dashboard analytics** (sections 3-5) — same reasoning as above; these
  share a lot of the plumbing from the Admin/Teacher work above, so they'll go faster once that
  plumbing (especially Recent Activities) exists.
- **The entire paper-size/orientation section** (sections 6-8: A3/A5/Letter/Legal/Foolscap/Custom
  sizes) — this is a separable, self-contained piece of work (it touches Result Display Settings,
  the PDF engine, and print CSS, not the dashboards at all), so it's cleaner as its own round.

None of this is guesswork on my part about what matters less — it's purely about not rushing
several genuinely different subsystems through in one pass. Tell me if you'd rather I reorder
what comes next.

## Testing

- New automated test suite: `tests/v88_scenarios.py` (16 checks, all passing) — covers the admin
  card's starting counts, tenant isolation between two schools, the teacher per-class table, the
  unspecified-gender reconciliation case, and a live transfer (deactivation) updating the numbers
  immediately.
- Re-ran the existing regression suite to confirm nothing else broke: `v87_scenarios.py` (63
  checks) plus a spot-check across `v60`, `v70`, `v75`, `v80`, `v85`, `v86` — all passing, 0
  failures.
- No database migration in this round — no new tables or columns were needed, so there's nothing
  extra to run on your live site beyond replacing the files below.

## Installing on PythonAnywhere

This round only changes three files, so the update is small:

```bash
cd ~/school-result-system
# (after uploading/extracting the new zip over your existing files, or editing these three)
```

Files changed: `app.py`, `templates/admin_dashboard.html`, `templates/teacher_dashboard.html`,
`static/css/style.css`. Then, as usual:

1. Reload your web app from the PythonAnywhere **Web** tab (or restart however you normally do).
2. Open the Admin Dashboard and confirm the Boys/Girls card shows sensible numbers for your
   school.
3. Open a Teacher account (or View As one) and confirm the Results workspace table now shows
   Students/Boys/Girls per class.

No backup is strictly required for this round since nothing touches the database, but if you'd
like to keep the habit, your usual `cp main.db main.db.bak-v88` before reloading is fine.

## What's next

Tell me which you'd like first — I'd lean toward **Phase 3 (Academic Performance Analytics)**
next since it's the other half of what makes the Admin/Teacher dashboards actually useful, but
it's your call. The full remaining queue, in the document's own order:

- Phase 3: School/class result performance trends, high-performing & needs-improvement class
  panels, teacher pass/fail statistics
- Phase 4: Recent Activities panels (Admin + Teacher) — including deciding how new activity types
  get recorded
- Phase 5: Student, Staff, and Parent dashboard analytics
- Phase 6-7: Result Display Settings paper sizes + automatic layout adjustment + matching print/PDF
- Phase 8: Final cross-cutting verification pass once everything above is built
